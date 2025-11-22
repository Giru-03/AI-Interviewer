import os
import uuid
import random
import json
import time
import io
from typing import TypedDict, List, Optional, Dict
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
import PyPDF2

load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = ChatGroq(model="llama-3.1-8b-instant")
checkpointer = MemorySaver()

class State(TypedDict):
    candidate_name: str
    role: str
    resume_text: str
    mode: str
    limit: int
    start_time: float
    difficulty_pools: Dict[str, List[dict]]
    current_difficulty: str
    questions_asked: int
    intro_done: bool
    current_question: Optional[str]
    current_area: Optional[str]
    current_diff: Optional[str]
    scores: List[int]
    transcript: List[dict]
    user_answer: Optional[str]
    previous_answer: Optional[str]
    previous_question: Optional[str]
    feedback: Optional[str]
    score: Optional[int]
    filler: Optional[str]
    is_end: bool
    needs_followup: bool

class AnswerRequest(BaseModel):
    thread_id: str
    answer: str

def clean_json_string(json_str):
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0]
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0]
    return json_str.strip()

def extract_text_from_pdf(file_content):
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        return text
    except:
        return ""

def prepare_question(state: State) -> State:
    if state["is_end"]: return state

    if not state["intro_done"]:
        state["current_question"] = "Tell me about yourself."
        state["current_area"] = "Introduction"
        state["current_diff"] = "easy"
        state["intro_done"] = True
        return state

    if state.get("current_area") == "Follow-up":
        state["current_question"] = "Thank you for that clarification. Should we move to the next question?"
        state["current_area"] = "Confirmation"
        return state

    if state["mode"] == "time":
        elapsed = time.time() - state["start_time"]
        if elapsed > (state["limit"] * 60): 
            state["is_end"] = True
            return state
    else:
        if state["questions_asked"] >= state["limit"]:
            state["is_end"] = True
            return state

    if state.get("needs_followup") and state.get("previous_answer") and state.get("current_area") != "Confirmation":
        prompt = f"""
        Generate a short, probing follow-up question based on this context.
        Previous Question: "{state['previous_question']}"
        Candidate Answer: "{state['previous_answer']}"
        
        The candidate's answer was either vague or very interesting. Ask for clarification or a specific example.
        Return ONLY the question text.
        """
        follow_up_q = llm.invoke(prompt).content
        state["current_question"] = follow_up_q
        state["current_area"] = "Follow-up"
        state["needs_followup"] = False 
        return state

    level = state["current_difficulty"]
    pools = state["difficulty_pools"]
    
    if not pools[level]:
        for other_level in ["medium", "hard", "easy"]:
            if pools[other_level]:
                level = other_level
                break
        else:
            state["is_end"] = True
            return state
    
    state["current_difficulty"] = level
    random.shuffle(pools[level])
    q_dict = pools[level].pop()
    
    state["current_question"] = q_dict["text"]
    state["current_area"] = q_dict["area"]
    state["current_diff"] = level
    state["questions_asked"] += 1
    
    return state

def human_feedback(state: State) -> State:
    return state 

def evaluate_and_generate_filler(state: State) -> State:
    q = state["current_question"]
    a = state["user_answer"] or ""
    current_area = state.get("current_area", "")

    state["previous_question"] = q
    state["previous_answer"] = a

    if current_area == "Confirmation":
        return {
            "score": None,
            "feedback": None,
            "filler": "Great, let's continue.",
            "needs_followup": False
        }

    if not a.strip() or a.lower().strip() in ["skip", "pass"]:
        return {
            "score": 0, 
            "feedback": "Skipped.", 
            "filler": "Okay, moving on.",
            "needs_followup": False
        }

    allow_followup = (current_area != "Follow-up")

    prompt_analysis = f"""
    You are an expert interviewer.
    Question: "{q}"
    Answer: "{a}"

    Output JSON: 
    {{
        "score": <int 0-100>, 
        "feedback": "<string>", 
        "filler": "<string natural conversational reaction>",
        "should_follow_up": <bool>
    }}
    
    Logic for should_follow_up:
    - Set true if answer is vague, too short, or highly intriguing but lacks detail.
    - Set false if answer is complete or completely irrelevant/nonsense.
    - Set false if logic says: {not allow_followup}
    """

    try:
        resp = llm.invoke(prompt_analysis, response_format={"type": "json_object"}).content
        data = json.loads(clean_json_string(resp))
        
        should_follow = data.get("should_follow_up", False)
        if not allow_followup: should_follow = False

        return {
            "score": data.get("score", 0),
            "feedback": data.get("feedback", "Error evaluating"),
            "filler": data.get("filler", "Okay."),
            "needs_followup": should_follow
        }
    except:
        return {
            "score": 0, 
            "feedback": "Evaluation Error", 
            "filler": "Okay.",
            "needs_followup": False
        }

def adjust_difficulty(state: State) -> State:
    if state.get("score") is not None:
        score = state["score"]
        current = state["current_difficulty"]
        if score >= 75 and current != "hard":
            state["current_difficulty"] = "hard" if current == "medium" else "medium"
        elif score < 45 and current != "easy":
            state["current_difficulty"] = "medium" if current == "hard" else "easy"
    return state

def process(state: State) -> State:
    if state.get("score") is not None and state.get("current_area") != "Confirmation":
        state["scores"].append(state["score"])
        
        entry = {
            "question": state['current_question'],
            "answer": state['user_answer'],
            "score": state['score'],
            "feedback": state['feedback'],
            "difficulty": state['current_diff']
        }
        state["transcript"].append(entry)
    
    return state

def decide(state: State) -> str:
    return END if state["is_end"] else "prepare_question"

builder = StateGraph(State)
builder.add_node("prepare_question", prepare_question)
builder.add_node("human_feedback", human_feedback)
builder.add_node("evaluate_and_generate_filler", evaluate_and_generate_filler)
builder.add_node("adjust_difficulty", adjust_difficulty)
builder.add_node("process", process)

builder.add_edge(START, "prepare_question")
builder.add_edge("prepare_question", "human_feedback")
builder.add_edge("human_feedback", "evaluate_and_generate_filler")
builder.add_edge("evaluate_and_generate_filler", "adjust_difficulty")
builder.add_edge("adjust_difficulty", "process")
builder.add_conditional_edges("process", decide, {END: END, "prepare_question": "prepare_question"})

app_graph = builder.compile(checkpointer=checkpointer, interrupt_before=["human_feedback"])

@app.post("/start_interview")
async def start_interview(
    name: str = Form(...),
    role: str = Form(...),
    mode: str = Form(...),
    limit: int = Form(...),
    resume: UploadFile = File(None)
):
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    resume_text = ""
    if resume:
        content = await resume.read()
        if resume.filename.endswith(".pdf"):
            resume_text = extract_text_from_pdf(content)
        else:
            resume_text = content.decode("utf-8")

    total_needed = limit * 3
    resume_q_count = 4 if resume_text else 0
    remaining = total_needed - resume_q_count
    tech_count = remaining // 2
    behav_count = remaining - tech_count

    gen_prompt = f"""
    Generate {total_needed} interview questions for a {role}.
    Candidate Name: {name}
    Resume Context: {resume_text[:2000]}...

    STRICT REQUIREMENTS:
    1. Create exactly {resume_q_count} questions based on resume.
    2. Create {tech_count} Technical questions.
    3. Create {behav_count} Behavioral questions.
    4. Mix Easy, Medium, Hard.
    
    Output JSON: {{ "questions": [ {{"text": "...", "area": "Resume/Technical/Behavioral", "difficulty": "easy/medium/hard"}} ] }}
    """
    
    try:
        resp = llm.invoke(gen_prompt, response_format={"type": "json_object"}).content
        data = json.loads(clean_json_string(resp))
        questions = data["questions"]
    except Exception:
        questions = [{"text": "What are your strengths?", "area": "Behavioral", "difficulty": "easy"}]

    pools = {"easy": [], "medium": [], "hard": []}
    for q in questions:
        d = q.get("difficulty", "medium").lower()
        if d in pools: pools[d].append(q)

    greeting = f"Hello {name}. "
    if resume_text:
        greeting += "I've reviewed your resume. "
    greeting += "Let's start."

    initial_state = {
        "candidate_name": name,
        "role": role,
        "resume_text": resume_text,
        "mode": mode,
        "limit": limit,
        "start_time": time.time(),
        "difficulty_pools": pools,
        "current_difficulty": "easy",
        "questions_asked": 0,
        "intro_done": False,
        "current_question": None,
        "current_area": None,
        "scores": [], "transcript": [],
        "user_answer": None, "feedback": None, "score": None, "filler": None,
        "is_end": False,
        "needs_followup": False,
        "previous_answer": None,
        "previous_question": None
    }

    for event in app_graph.stream(initial_state, config): pass
    
    snapshot = app_graph.get_state(config)
    first_q = snapshot.values.get("current_question")
    full_message = f"{greeting} {first_q}"

    return {
        "thread_id": thread_id,
        "message": full_message,
        "is_end": False
    }

@app.post("/submit_answer")
async def submit_answer(req: AnswerRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    
    app_graph.update_state(config, {"user_answer": req.answer}, as_node="human_feedback")
    
    filler_text = ""
    for event in app_graph.stream(None, config):
        if 'evaluate_and_generate_filler' in event:
            filler_text = event['evaluate_and_generate_filler'].get('filler', "")

    snapshot = app_graph.get_state(config)
    state = snapshot.values
    
    if not snapshot.next:
        summary_prompt = f"""
        You are an expert Interview Coach.
        Review the transcript: {json.dumps(state['transcript'])}
        
        Generate a detailed feedback report in JSON format.
        Output JSON Structure:
        {{
            "summary": "3 sentence executive summary of performance.",
            "strengths": ["Strength 1", "Strength 2", "Strength 3"],
            "areas_for_improvement": ["Improvement 1", "Improvement 2", "Improvement 3"],
            "communication_rating": "Excellent/Good/Average/Poor",
            "technical_rating": "Excellent/Good/Average/Poor"
        }}
        """
        
        try:
            resp = llm.invoke(summary_prompt, response_format={"type": "json_object"}).content
            report_json = json.loads(clean_json_string(resp))
        except Exception:
            report_json = {
                "summary": "Interview complete.",
                "strengths": ["Completed session"],
                "areas_for_improvement": ["Practice specifics"],
                "communication_rating": "Good",
                "technical_rating": "Good"
            }

        return {
            "is_end": True, 
            "filler": f"{filler_text} That concludes our interview. Thank you.",
            "message": "Interview Complete.", 
            "report_data": {
                "details": report_json,
                "transcript": state["transcript"],
                "scores": state["scores"]
            }
        }
    
    return {
        "is_end": False,
        "filler": filler_text,
        "message": state.get("current_question"),
        "report_data": None
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)