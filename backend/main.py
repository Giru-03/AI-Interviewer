import os
import uuid
import time
import io
import json
from typing import List, Dict
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field, SecretStr
import edge_tts
import cloudinary
import cloudinary.uploader

load_dotenv()

cloudinary.config(
  cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
  api_key = os.getenv('CLOUDINARY_API_KEY'),
  api_secret = os.getenv('CLOUDINARY_API_SECRET')
)

class FeedbackDetail(BaseModel):
    question: str
    feedback: str
    relevance_score: int
    clarity_score: int
    technical_accuracy_score: int
    overall_score: int

class InterviewReport(BaseModel):
    summary: str = Field(description="Professional summary of the candidate")
    communication_rating: int = Field(description="Average clarity score out of 10")
    technical_rating: int = Field(description="Average technical accuracy score out of 10")
    culture_fit_rating: int = Field(description="Estimated culture fit score out of 10")
    strengths: List[str]
    areas_for_improvement: List[str]
    transcript_analysis: List[FeedbackDetail]

class TextInteraction(BaseModel):
    session_id: str
    text: str
    is_silence: bool = False 

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

groq_key = os.environ.get("GROQ_API_KEY")
llm = ChatGroq(
    temperature=0.6,
    model="llama-3.1-8b-instant",
    api_key=SecretStr(groq_key) if groq_key else None
)

llm_strict = ChatGroq(
    temperature=0.0,
    model="llama-3.1-8b-instant",
    api_key=SecretStr(groq_key) if groq_key else None
)

class InterviewSession:
    def __init__(self, name: str, role: str, resume_text: str, duration_minutes: int, mode: str = "voice"):
        self.id = str(uuid.uuid4())
        self.name = name
        self.role = role
        self.resume_text = resume_text or "No resume provided."
        self.duration_minutes = float(duration_minutes)
        self.start_time = time.time()
        self.memory = InMemoryChatMessageHistory()
        self.finished = False
        self.mode = mode

        style_instruction = ""
        if mode == "chat":
            style_instruction = "You are chatting via text. Do NOT use spoken fillers like 'umm', 'ah', 'hmm'. Keep your responses concise, professional, and grammatically perfect."
        else:
            style_instruction = "You are speaking via voice. Use natural spoken fillers occasionally (like 'umm', 'ah') to sound human, but keep it professional."

        system_context = f"""
You are an expert professional interviewer conducting a strict time-bound screening interview for a {role} position.
Candidate: {name}
Total interview duration: {duration_minutes} minutes
Resume: {self.resume_text[:3500]}
Mode: {mode.upper()}

{style_instruction}

THIS INTERVIEW IS STRICTLY TIME-LIMITED. You MUST pace questions to finish on time.

Time allocation (adjust based on total duration):
- 0–10% of time: Greeting + "Tell me about yourself"
- 10–35% of time: 2–3 experience/resume-based questions
- 35–75% of time: 3–4 deep technical questions specific to {role}
- 75–90% of time: 1 behavioral/situational question
- Last 10%: Closing and thank you

CRITICAL RULES:
- Ask exactly ONE question at a time
- Never ask follow-ups unless answer is completely off-topic or empty
- Keep every response under 3 sentences
- Track time mentally — do NOT ask all questions if time is running out
- When less than 10% time remains, immediately move to closing
- Do NOT output internal notes, parentheses, or meta-commentary (e.g., "(Note: ...)", "[Silence detected]"). Speak ONLY to the candidate.
- If the user is silent (indicated by [SILENCE]), prompt them gently (e.g., "Are you still there?", "Would you like me to repeat the question?") or move to the next question if appropriate.
- At the very end, always say: "Thank you for your time. This concludes the interview."

You are now starting the interview.
"""
        self.memory.add_message(SystemMessage(content=system_context))

    def get_remaining_time(self):
        elapsed = (time.time() - self.start_time) / 60
        remaining = self.duration_minutes - elapsed
        return max(0.0, remaining)

    async def get_response(self, user_input: str, is_silence: bool = False):
        if is_silence:
            self.memory.add_message(HumanMessage(content="[SILENCE]"))
        else:
            self.memory.add_message(HumanMessage(content=user_input))

        messages = self.memory.messages
        remaining = self.get_remaining_time()

        if self.finished:
             return "The interview has already concluded. Thank you."

        if remaining <= 0:
            self.finished = True
            farewell = "Thank you for your time today. This concludes our interview. Goodbye!"
            self.memory.add_message(AIMessage(content=farewell))
            return farewell

        if remaining < (self.duration_minutes * 0.10):
            self.finished = True
            closing = "We're out of time. Thank you so much for your responses today. This concludes the interview."
            self.memory.add_message(AIMessage(content=closing))
            return closing

        response = await llm.ainvoke(messages)
        resp_content = response.content if isinstance(response.content, str) else json.dumps(response.content)
        
        lower_resp = resp_content.lower()
        if "concludes the interview" in lower_resp or "concludes our interview" in lower_resp or "thank you for your time" in lower_resp:
             self.finished = True

        self.memory.add_message(AIMessage(content=resp_content))
        return resp_content

sessions: Dict[str, InterviewSession] = {}

async def generate_audio(text: str, session_id: str):
    if not text or not text.strip():
        return None
    
    temp_filename = f"/tmp/temp_resp_{session_id}_{int(time.time())}.mp3"
    
    try:
        communicate = edge_tts.Communicate(text, "en-US-AndrewNeural")
        await communicate.save(temp_filename)
        
        upload_result = cloudinary.uploader.upload(
            temp_filename, 
            resource_type="video", 
            folder="interview_audio",
            public_id=f"audio_{session_id}_{int(time.time())}"
        )
        return upload_result.get("secure_url")

    except Exception as e:
        print(f"Audio Generation/Upload Error: {e}")
        return None
    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except:
                pass

def extract_text_from_pdf(file_bytes):
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        print(f"PDF Extraction Error: {e}")
        return ""

@app.post("/start_interview")
async def start_interview(
    name: str = Form(...),
    role: str = Form(...),
    duration: int = Form(...),
    mode: str = Form("voice"),
    resume: UploadFile = File(None)
):
    if duration < 3 or duration > 45:
        raise HTTPException(status_code=400, detail="Duration must be between 3 and 45 minutes.")

    resume_text = ""
    if resume and resume.file:
        content = await resume.read()
        if len(content) > 0:
            resume_text = extract_text_from_pdf(content)
    
    if not resume_text or len(resume_text.strip()) < 10:
        print("Validation Failed: No meaningful text extracted from PDF.")
        raise HTTPException(status_code=400, detail="Could not extract readable text from the resume. Please upload a valid text-based PDF.")
    
    name_parts = name.strip().lower().split()
    resume_lower = resume_text.lower()
    
    if not all(part in resume_lower for part in name_parts):
        print(f"Validation Failed: Name '{name}' not found in resume text (length: {len(resume_text)} chars).")
        raise HTTPException(
            status_code=400, 
            detail=f"The name '{name}' does not match the resume content. Please enter the name exactly as it appears."
        )

    session = InterviewSession(name, role, resume_text, duration, mode)
    sessions[session.id] = session

    greeting = f"Hello {name}, thank you for joining me. This is a {duration}-minute timed interview for the {role} position. We'll begin now — please tell me about yourself and your background."
    session.memory.add_message(AIMessage(content=greeting))

    audio_url = None
    if mode == "voice":
        audio_url = await generate_audio(greeting, session.id)

    return {
        "session_id": session.id,
        "text": greeting,
        "audio_url": audio_url or "",
        "mode": mode
    }

@app.post("/process_audio")
async def process_audio(
    session_id: str = Form(...),
    file: UploadFile = File(...)
):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    user_text = ""
    is_silence = False

    temp_file = f"/tmp/temp_{uuid.uuid4()}.webm"
    try:
        contents = await file.read()
        if len(contents) > 1024:
            with open(temp_file, "wb") as f:
                f.write(contents)

            from groq import Groq
            client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
            with open(temp_file, "rb") as audio:
                transcription = client.audio.transcriptions.create(
                    file=(temp_file, audio.read()),
                    model="whisper-large-v3-turbo",
                    language="en",
                    temperature=0.0,
                )
            user_text = transcription.text.strip()
    except Exception as e:
        print(f"Transcription error: {e}")
        user_text = ""
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

    if not user_text or len(user_text.strip()) < 3:
        is_silence = True
        user_text = "[SILENCE]"

    ai_response = await session.get_response(user_text, is_silence)
    
    audio_url = ""
    if session.mode == "voice":
        audio_url = await generate_audio(ai_response, session.id)

    return {
        "finished": session.finished,
        "user_text": user_text if not is_silence else "[SILENCE]",
        "ai_text": ai_response,
        "audio_url": audio_url or ""
    }

@app.post("/process_text")
async def process_text(interaction: TextInteraction):
    if interaction.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions[interaction.session_id]
    
    ai_response = await session.get_response(interaction.text, is_silence=interaction.is_silence)
    
    return {
        "finished": session.finished,
        "ai_text": ai_response
    }

@app.get("/generate_report/{session_id}")
async def generate_report(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    transcript = ""
    for msg in session.memory.messages:
        if isinstance(msg, HumanMessage):
            content = msg.content
            if content == "[SILENCE]" or content == "":
                content = "[No Response / Silence]"
            
            cand = content if isinstance(content, str) else json.dumps(content)
            transcript += f"Candidate: {cand}\n"
        elif isinstance(msg, AIMessage):
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
            content = content.strip()
            if content and "thank you for joining" not in content.lower() and "this concludes" not in content.lower():
                transcript += f"Interviewer: {content}\n"

    if len(transcript.strip()) < 50:
        return JSONResponse(content={
            "summary": "Interview ended early or insufficient responses provided.",
            "communication_rating": 0,
            "technical_rating": 0,
            "culture_fit_rating": 0,
            "strengths": ["N/A"],
            "areas_for_improvement": ["Interview was not completed"],
            "transcript_analysis": []
        })

    parser = JsonOutputParser(pydantic_object=InterviewReport)

    prompt = ChatPromptTemplate.from_template("""
You are an expert hiring manager evaluating a timed technical interview.

Analyze the full transcript below. 
**IMPORTANT**: If the candidate's response is labeled "[No Response / Silence]", you MUST give them a score of 0 for that question and note that they did not answer. Do NOT hallucinate an answer for them.

Analyze the transcript and for each meaningful question-answer pair provide details.
**Strictly return a JSON object** with the following fields:
- summary (string)
- communication_rating (int)
- technical_rating (int)
- culture_fit_rating (int)
- strengths (list of strings)
- areas_for_improvement (list of strings)
- transcript_analysis (list of objects with details)

Transcript:
{transcript}

{format_instructions}
""")

    chain = prompt | llm_strict | parser

    try:
        report = await chain.ainvoke({
            "transcript": transcript,
            "format_instructions": parser.get_format_instructions()
        })
        
        try:
            if session_id in sessions:
                del sessions[session_id]
        except Exception as e:
            print(f"Failed to remove session {session_id} from memory: {e}")

        return JSONResponse(content=report)
    except Exception as e:
        print(f"Report error: {e}")
        return JSONResponse(content={
            "summary": "Error analyzing interview transcript.",
            "communication_rating": 0,
            "technical_rating": 0,
            "culture_fit_rating": 0,
            "strengths": ["Analysis failed"],
            "areas_for_improvement": ["Please try again"],
            "transcript_analysis": []
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)