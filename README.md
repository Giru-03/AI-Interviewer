# AI Interviewer Agent

An intelligent AI agent designed to help users prepare for job interviews by conducting mock interviews, asking relevant follow-up questions, and providing detailed feedback.

## 🚀 Features

-   **Role-Specific Mock Interviews**: Conducts interviews tailored to specific job roles (e.g., Sales, Software Engineer, Product Manager).
-   **Dynamic Follow-up Questions**: Uses advanced LLMs to ask context-aware follow-up questions based on your responses, simulating a real interviewer.
-   **Multi-Modal Interaction**:
    -   **Voice Mode (Preferred)**: Speak naturally with the AI using speech-to-text and text-to-speech capabilities.
    -   **Chat Mode**: Text-based interaction for a quieter environment.
-   **Comprehensive Feedback**: Generates a detailed report after the session, including:
    -   Communication, Technical, and Culture Fit ratings.
    -   Strengths and Areas for Improvement.
    -   Question-by-question analysis with relevance and clarity scores.
-   **Resume Integration**: Upload your resume (PDF) to get personalized questions based on your experience.

## 🛠️ Tech Stack

### Backend
-   **FastAPI**: High-performance web framework for building APIs.
-   **LangChain**: Framework for developing applications powered by language models.
-   **Groq (Llama 3.1)**: Ultra-fast LLM inference for real-time conversational capabilities.
-   **Redis**: In-memory data structure store used for scalable session management.
-   **Cloudinary**: Cloud storage for handling audio files.
-   **Murf.ai**: High-quality text-to-speech synthesis for professional voice interaction.

### Frontend
-   **React (Vite)**: Modern, fast frontend build tool and library.
-   **Chart.js**: For visualizing interview performance scores.
-   **Lucide React**: Beautiful and consistent icons.
-   **Web Audio API**: For real-time voice recording and silence detection.

## 🏗️ Architecture

The application follows a decoupled client-server architecture:

1.  **Frontend**: A React SPA handles user input (voice/text), manages the interview session state, and displays the final report. It uses the Web Audio API for silence detection to automatically send voice input when the user stops speaking.
2.  **Backend**: A FastAPI server manages the interview logic.
    -   **Session Management**: Uses **Redis** for scalable, distributed session storage (with automatic fallback to in-memory for local dev).
    -   **LLM Integration**: Uses LangChain and Groq to generate interviewer responses and analyze the final transcript.
    -   **Audio Processing**: Handles speech-to-text (transcription) and text-to-speech (response generation).

## 📂 Project Structure

```
AI-Interviewer/
├── backend/
│   ├── api/
│   │   └── index.py        # Main FastAPI application and logic
│   ├── requirements.txt    # Python dependencies
│   └── vercel.json         # Deployment config
├── frontend/
│   ├── src/
│   │   ├── components/     # React components (Chat, Voice, Setup, Report)
│   │   ├── context/        # Context providers (Toast)
│   │   ├── App.jsx         # Main application component
│   │   └── main.jsx        # Entry point
│   ├── package.json        # Node.js dependencies
│   └── vite.config.js      # Vite configuration
└── README.md               # Project documentation
```

## ⚙️ Setup Instructions

### Prerequisites
-   Python 3.8+
-   Node.js 16+
-   Groq API Key
-   Cloudinary Credentials
-   Murf API Key

### Backend Setup

1.  Navigate to the backend directory:
    ```bash
    cd backend
    ```
2.  Create a virtual environment (optional but recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Create a `.env` file in the `backend` directory with your API keys:
    ```env
    GROQ_API_KEY=your_groq_api_key
    CLOUDINARY_CLOUD_NAME=your_cloud_name
    CLOUDINARY_API_KEY=your_api_key
    CLOUDINARY_API_SECRET=your_api_secret
    MURF_API_KEY=your_murf_api_key
    REDIS_URL=redis://localhost:6379 # Optional: For production session storage
    ```
5.  Run the server:
    ```bash
    uvicorn api.index:app --reload
    ```

### Frontend Setup

1.  Navigate to the frontend directory:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Start the development server:
    ```bash
    npm run dev
    ```

## 🧠 Design Decisions

-   **Groq for LLM**: Chosen for its exceptional speed, which is critical for maintaining a natural flow in voice conversations. Latency is a major UX killer in voice bots, and Groq minimizes this.
-   **Murf.ai for TTS**: Selected for its professional and high-quality voice synthesis, providing a clear and engaging interviewer persona.
-   **Redis for Scalability**: Implemented a robust session store using Redis. This allows the application to handle multiple concurrent users and scale horizontally across multiple server instances. It includes pipeline optimizations to minimize latency.
-   **Client-Side Silence Detection**: Instead of streaming audio continuously to the server (which is complex and costly), the frontend detects silence. When the user stops speaking for a set threshold, the audio chunk is sent for processing. This balances complexity and responsiveness.
-   **Anti-Hallucination Measures**: The report generation prompt is strictly engineered to prevent "fake" reports. If a user is silent or the transcript is insufficient, the system explicitly returns a score of 0 and marks the interview as incomplete, ensuring honest feedback.
-   **Separation of Concerns**: The frontend handles all media capture and playback, while the backend focuses purely on intelligence and logic.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
