"""Example inbound Guava voice agent, scaffolded by `guava create`.

Run `guava run` from your project directory to call in and talk to it. Edit the
tasks and handlers below, then re-run to hear your changes.
"""

import logging
from pathlib import Path

import guava
from guava import logging_utils
from guava.events import BotSessionEnded
from guava.helpers.rag import DocumentQA

logger = logging.getLogger("guava.intro_agent")

CURRENT_DIR = Path(__file__).resolve().parent

try:
    with open(CURRENT_DIR / "guava-docs.md") as f:
        document_qa = DocumentQA(documents=f.read(), namespace="guava-cli-intro")

except Exception as exc:
    document_qa = None
    logger.warning("Could not load Guava docs for RAG: %s", exc)

agent = guava.Agent(
    purpose=(
        "You are an example voice agent shipped with the Guava CLI to show "
        "the user they've successfully launched a working agent. Answer their "
        "questions about the Guava platform, SDK, and CLI from your connected "
        "knowledge base."
    ),
)


@agent.on_call_start
def on_call_start(call: guava.Call):
    logger.info("Call started (session: %s)", call.id)
    call.set_task(
        "intro",
        objective=(
            "Walk the caller through a short introduction, then shift to "
            "answering their questions about Guava from your knowledge base. "
            "Complete the task once they have no more questions."
        ),
        checklist=[
            guava.Say(
                "Hi! I'm a Guava voice agent, and you just launched me "
                "using the Guava CLI. I can answer your questions about "
                "using Guava."
            ),
            guava.Field(
                key="user_name",
                field_type="text",
                description=(
                    "Transition with 'But first,' then ask the caller for their name "
                    "so you can address them personally."
                ),
                required=False,
            ),
            "Answer any questions the caller has about Guava.",
            "Once the caller has no more questions, welcome them to Guava. "
            "Point them to the Guava docs and examples library as resources "
            "for building their own agent. Express that the team would love "
            'to "hear what you build." Close warmly.',
        ],
    )


@agent.on_question
def on_question(call: guava.Call, question: str) -> str:
    logger.info("Question received: %s", question)
    if document_qa is not None:
        answer = document_qa.ask(question)
    else:
        answer = (
            "Unfortunately, I'm not able to answer that question right now, "
            "because my knowledge base didn't load. To fix that, I recommend "
            "verifying your network connection, then relaunching me."
        )
    logger.info("Answering...")
    return answer


@agent.on_task_complete("intro")
def on_intro_complete(call: guava.Call):
    user_name = call.get_field("user_name")
    if user_name:
        logger.info("Intro task complete. Caller name: %s", user_name)
    else:
        logger.info("Intro task complete.")
    call.hangup()


@agent.on_session_end
def on_session_end(call: guava.Call, event: BotSessionEnded):
    logger.info("Session ended (session: %s)", call.id)


if __name__ == "__main__":
    logging_utils.configure_logging()

    # Run this to attach your agent to a phone number. Call your agent's number to talk to it.
    agent.listen_phone("+12402126155")

    # Run this to talk to your agent using your local audio device.
    # agent.call_local()

    # Run this to receive a WebRTC link where you can talk to your agent in the browser.
    # agent.listen_webrtc()

    # Run this to test your agent in a text-based chat session in the terminal (no audio required).
    # agent.chat()
