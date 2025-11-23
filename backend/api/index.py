import os
import uuid
import time
import io
import json
import tempfile
from typing import List, Dict, Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pypdf import PdfReader
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, messages_to_dict, messages_from_dict
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field, SecretStr
import requests
import redis
import cloudinary
import cloudinary.uploader
from groq import Groq

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
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

class SessionStore:
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL")
        self.redis_client = None
        self.local_cache = {}
        
        if self.redis_url:
            try:
                self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
                # Test connection immediately to catch auth errors early
                self.redis_client.ping()
                print("Connected to Redis")
            except Exception as e:
                print(f"Failed to connect to Redis: {e}")
                self.redis_client = None # Fallback to local cache on error

    def save(self, session: InterviewSession):
        if self.redis_client:
            # Optimize: Only save if messages changed or it's a new session
            # For now, we just save asynchronously or use pipeline if possible, 
            # but since this is sync redis, we can just optimize what we send.
            
            msgs = messages_to_dict(session.memory.messages)
            data = {
                "id": session.id,
                "name": session.name,
                "role": session.role,
                "resume_text": session.resume_text,
                "duration_minutes": str(session.duration_minutes),
                "start_time": str(session.start_time),
                "finished": str(session.finished),
                "mode": session.mode,
                "messages": json.dumps(msgs)
            }
            # Use pipeline to reduce round trips
            pipe = self.redis_client.pipeline()
            pipe.hset(f"session:{session.id}", mapping=data)
            pipe.expire(f"session:{session.id}", 3600)
            pipe.execute()
        else:
            self.local_cache[session.id] = session

    def get(self, session_id: str) -> Optional[InterviewSession]:
        # Check local cache first for speed (optional optimization, but risky if scaling horizontally)
        # For now, we stick to Redis for truth, but we can optimize the fetch.
        
        if self.redis_client:
            # Use pipeline to check existence and get data in one go? 
            # Actually hgetall returns empty dict if key doesn't exist, so we can skip exists check.
            data = self.redis_client.hgetall(f"session:{session_id}")
            
            if not data:
                return None
            
            session = InterviewSession(
                name=data["name"],
                role=data["role"],
                resume_text=data["resume_text"],
                duration_minutes=int(float(data["duration_minutes"])),
                mode=data.get("mode", "voice")
            )
            session.id = data["id"]
            session.start_time = float(data["start_time"])
            session.finished = data["finished"] == "True"
            
            msgs = messages_from_dict(json.loads(data["messages"]))
            session.memory.clear() 
            for m in msgs:
                session.memory.add_message(m)
                
            return session
        else:
            return self.local_cache.get(session_id)

session_store = SessionStore()

async def generate_audio(text: str, session_id: str):
    if not text or not text.strip():
        return None

    api_key = os.getenv("MURF_API_KEY")
    voice_id = os.getenv("MURF_VOICE_ID", "en-US-cooper")  

    if not api_key:
        print("MURF_API_KEY not set")
        return None

    url = "https://api.murf.ai/v1/speech/generate"

    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }

    payload = {
        "voiceId": voice_id,
        "text": text,
        "style": "Promo",
        "rate": 0,
        "pitch": 0,
        "sampleRate": 48000,
        "format": "MP3",
        "channel": "MONO"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        audio_url = data.get("audioFile")
        
        if not audio_url:
            print("Murf API did not return an audio URL")
            return None

        # Upload the URL directly to Cloudinary
        upload_result = cloudinary.uploader.upload(
            audio_url,
            resource_type="video",
            folder="interview_audio",
            public_id=f"audio_{session_id}_{int(time.time())}",
            format="mp3"
        )
        return upload_result.get("secure_url")

    except Exception as e:
        print(f"Murf TTS Error: {e}")
        return None

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

@app.get("/")
async def root():
    return {"message": "Interview AI Backend Running"}

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
    if resume and resume.filename:
        content = await resume.read()
        if len(content) > 0:
            resume_text = extract_text_from_pdf(content)

    if not resume_text or len(resume_text.strip()) < 10:
        resume_text = "No resume provided."

    session = InterviewSession(name, role, resume_text, duration, mode)
    session_store.save(session)

    greeting = f"Hello {name}, thank you for joining me. This is a {duration}-minute timed interview for the {role} position. We'll begin now — please tell me about yourself and your background."
    session.memory.add_message(AIMessage(content=greeting))
    session_store.save(session)

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
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    user_text = ""
    is_silence = False

    temp_file_path = os.path.join(tempfile.gettempdir(), f"temp_{uuid.uuid4()}.webm")
    
    try:
        contents = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(contents)

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        with open(temp_file_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3-turbo",
                language="en",
                temperature=0.0,
            )
            user_text = transcription.text.strip()
    except Exception as e:
        print(f"Transcription error: {e}")
        user_text = ""
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

    if not user_text or len(user_text.strip()) < 3:
        is_silence = True
        user_text = "[SILENCE]"

    ai_response = await session.get_response(user_text, is_silence)
    session_store.save(session)
    
    audio_url = ""
    if session.mode == "voice":
        audio_url = await generate_audio(ai_response, session.id)

    return {
        "finished": session.finished,
        "user_text": "[SILENCE]" if is_silence else user_text,
        "ai_text": ai_response,
        "audio_url": audio_url or ""
    }

@app.post("/process_text")
async def process_text(interaction: TextInteraction):
    session = session_store.get(interaction.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    ai_response = await session.get_response(interaction.text, interaction.is_silence)
    session_store.save(session)
    
    return {
        "finished": session.finished,
        "ai_text": ai_response
    }

@app.get("/generate_report/{session_id}")
async def generate_report(session_id: str):
    session = session_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    transcript = ""
    for msg in session.memory.messages:
        if isinstance(msg, HumanMessage):
            content = msg.content
            if content in ("[SILENCE]", "", None):
                content = "[No Response / Silence]"
            transcript += f"Candidate: {content}\n"
        elif isinstance(msg, AIMessage):
            content = str(msg.content).strip()
            if content and "thank you for joining" not in content.lower() and "this concludes" not in content.lower():
                transcript += f"Interviewer: {content}\n"

    if len(transcript.strip()) < 50:
        return JSONResponse(content={
            "summary": "Insufficient responses provided.",
            "communication_rating": 0,
            "technical_rating": 0,
            "culture_fit_rating": 0,
            "strengths": ["N/A"],
            "areas_for_improvement": ["Did not complete the interview"],
            "transcript_analysis": []
        })

    parser = JsonOutputParser(pydantic_object=InterviewReport)

    prompt = ChatPromptTemplate.from_template("""
You are an expert hiring manager evaluating a timed technical interview.

Analyze the full transcript below. 
**CRITICAL INSTRUCTIONS**:
1. **NO HALLUCINATIONS**: If the transcript is empty, short, or contains mostly "[No Response / Silence]", return a report explicitly stating that the interview was incomplete.
2. **ZERO TOLERANCE FOR SILENCE**: If the candidate's response is labeled "[No Response / Silence]", you MUST give them a score of 0 for that question.
3. **FACTUAL ANALYSIS ONLY**: Do not invent strengths or improvements. Only base them on the actual words spoken by the candidate.
4. **STRICT SCORING**: If the candidate did not answer technical questions, the technical_rating MUST be 0.

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
        return JSONResponse(content=report)
    except Exception as e:
        print(f"Report generation error: {e}")
        return JSONResponse(content={
            "summary": "Error analyzing interview transcript.",
            "communication_rating": 0,
            "technical_rating": 0,
            "culture_fit_rating": 0,
            "strengths": ["Analysis failed"],
            "areas_for_improvement": ["Please try again later"],
            "transcript_analysis": []
        })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)