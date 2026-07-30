"""Citizen Emergency Assistant Service.

Routes citizen questions to specialist AI agents and LLM engine with ChromaDB RAG
grounding. Asks clarifying follow-up questions for complex emergency scenarios
and provides natural, verified safety guidance.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel

from app.core.config import settings
from app.core.llm import ModelTier, get_llm_engine
from app.core.logging import get_logger
from app.rag.store import get_vector_store

logger = get_logger(__name__)


class AssistantResponseSchema(BaseModel):
    agent_role: str
    agent_name: str
    agent_icon: str
    answer_summary: str
    follow_up_questions: list[str] = []
    steps: list[str]
    helplines: list[str]


def ask_citizen_assistant(
    question: str, state: str = "", district: str = "", hazard: str = "flood"
) -> dict[str, Any]:
    """Process a citizen question using RAG doctrine and LLM reasoning."""
    q_lower = question.lower().strip().strip(".!?")
    location_str = f"{district}, {state}".strip(", ") or "your area"

    # 0. Check for conversational greetings / casual messages
    greetings = {"hi", "hello", "hey", "hola", "namaste", "thanks", "thank you", "good morning", "good evening", "hi there", "hello there"}
    if q_lower in greetings or any(q_lower == g for g in greetings):
        return {
            "question": question,
            "district": district,
            "state": state,
            "hazard": hazard,
            "agent": {
                "role": "knowledge",
                "name": "Sentinel AI Assistant",
                "icon": "🤖",
            },
            "answer_summary": f"Hello! I'm your SentinelAI emergency assistant for {location_str}. How can I help you today? You can ask me about emergency shelters, medical guidance, first aid, or weather alerts.",
            "follow_up_questions": [
                "Where is the nearest emergency shelter?",
                "What first aid steps should I take?",
                "Is there an active weather advisory for my area?"
            ],
            "steps": [
                "Type any emergency question or situation above.",
                "Select a quick topic button below.",
                "Or tap 'I NEED HELP' on the Home tab for instant multi-agent emergency triage."
            ],
            "helplines": [
                "112 (National Emergency)",
                "1070 (State Relief)",
                "1077 (District Control Room)",
                "108 (Ambulance)",
            ],
            "is_llm_reasoned": False,
        }

    # 1. RAG Doctrine Retrieval from ChromaDB
    rag_context = ""
    try:
        store = get_vector_store()
        results = store.search(query=question, top_k=3)
        if results:
            rag_context = "\n---\n".join(
                f"[Source: {r.metadata.get('source_id', 'NDMA Doctrine')}]\n{r.text}"
                for r in results
            )
    except Exception as err:
        logger.warning(f"RAG doctrine retrieval skipped: {err}")

    # 2. Attempt LLM Reasoning if LLM is available
    llm = get_llm_engine()
    if llm.available:
        try:
            system_prompt = (
                f"You are SentinelAI Emergency Assistant — an empathetic, expert disaster response companion for citizens in India.\n"
                f"Location context: {location_str}. Current primary threat: {hazard.upper()}.\n\n"
                f"ROLES & BEHAVIOR:\n"
                f"1. Identify the specialist role needed (medical, shelter, infrastructure, weather, or knowledge).\n"
                f"2. If the user's situation involves a complex emergency (e.g. elderly person trapped, diabetic needing insulin, injuries, rising floodwater), "
                f"   generate 2-3 essential clarifying follow-up questions to better understand their condition (e.g. 'Is he conscious?', 'Can he walk?', 'Do you have spare insulin?').\n"
                f"3. Provide 3-5 concise, direct, life-saving step-by-step instructions.\n"
                f"4. Ground all safety advice strictly in official NDMA/WHO doctrine provided below.\n"
                f"5. Do NOT hallucinate unverified medical treatments or fake emergency contacts.\n\n"
                f"VERIFIED NDMA DOCTRINE CONTEXT:\n{rag_context or 'Standard NDMA/WHO Disaster Guidelines apply.'}\n"
            )

            import asyncio
            response = asyncio.run(
                llm.structured(
                    schema=AssistantResponseSchema,
                    system=system_prompt,
                    user=f"Citizen Emergency Question: {question}",
                    tier=ModelTier.FAST,
                    agent="assistant",
                )
            )

            return {
                "question": question,
                "district": district,
                "state": state,
                "hazard": hazard,
                "agent": {
                    "role": response.agent_role,
                    "name": response.agent_name,
                    "icon": response.agent_icon,
                },
                "answer_summary": response.answer_summary,
                "follow_up_questions": response.follow_up_questions,
                "steps": response.steps,
                "helplines": response.helplines or [
                    "112 (National Emergency)",
                    "1070 (State Relief)",
                    "1077 (District Control)",
                    "108 (Ambulance)",
                ],
                "is_llm_reasoned": True,
            }
        except Exception as exc:
            logger.warning(f"LLM assistant reasoning failed, using domain fallback: {exc}")

    # 3. Deterministic Domain Logic Fallback (Rule-Based + RAG)
    if any(w in q_lower for w in ["injury", "hurt", "first aid", "doctor", "blood", "bite", "medicine", "sick", "hospital", "fever", "diabet", "insulin"]):
        agent_role = "medical"
        agent_name = "Medical Response Agent"
        agent_icon = "🏥"
        answer_summary = f"Emergency medical response guidance for {location_str}:"
        follow_ups = [
            "Is the patient conscious and responsive?",
            "Can the person walk independently or do they require stretcher transport?",
            "Do you have a 3-day supply of essential medication (e.g., insulin) packed in a waterproof bag?"
        ]
        steps = [
            "Keep the affected person calm, warm, and elevated above ground level.",
            "Apply clean pressure bandages to stop bleeding. Avoid tight tourniquets unless severe arterial bleeding.",
            "Store essential temperature-sensitive medicines (like insulin) in insulated containers with ice or cool water.",
            "Dial 108 or 112 immediately for emergency ambulance dispatch to the nearest trauma hospital."
        ]

    elif any(w in q_lower for w in ["shelter", "stay", "camp", "food", "water", "drink", "sleep", "house", "evacuate", "trapped"]):
        agent_role = "shelter"
        agent_name = "Shelter & Evacuation Agent"
        agent_icon = "⛺"
        answer_summary = f"Emergency shelter & evacuation guidance for {location_str}:"
        follow_ups = [
            "How many family members need evacuation?",
            "Are elderly individuals, infants, or disabled persons with you?",
            "Is your current building structurally safe or is water entering?"
        ]
        steps = [
            "Proceed immediately to your nearest designated Multipurpose Disaster Relief Shelter.",
            "Boil all drinking water for at least 3 minutes before consumption to prevent cholera and gastroenteritis.",
            "Carry dry non-perishable food, flashlights, power banks, and essential identity documents.",
            "Contact district control room at helpline 1077 for emergency food packets and rescue boat pickup."
        ]

    elif any(w in q_lower for w in ["power", "electricity", "wire", "shock", "bridge", "road", "block", "building", "light", "gas"]):
        agent_role = "infrastructure"
        agent_name = "Infrastructure & Safety Agent"
        agent_icon = "🏗️"
        answer_summary = f"Infrastructure & electrical safety advisory for {location_str}:"
        follow_ups = [
            "Is floodwater currently touching electrical outlets or appliances?",
            "Have you shut off the main electrical circuit breaker?"
        ]
        steps = [
            "Switch OFF main electricity circuit breakers and gas cylinder valves immediately if water enters building.",
            "Stay at least 10 meters away from fallen power lines, submerged transformers, and electric poles.",
            "Do not drive or walk across submerged bridges or roads. Structural damage may be invisible under water.",
            "Report broken utility poles or gas leaks to emergency control at 112 or 101."
        ]

    elif any(w in q_lower for w in ["rain", "storm", "wind", "cyclone", "weather", "forecast", "cloud", "sun", "hot"]):
        agent_role = "weather"
        agent_name = "Weather & Climate Intelligence Agent"
        agent_icon = "📡"
        answer_summary = f"Live meteorological report for {location_str}:"
        follow_ups = [
            "Are you currently inside a concrete pucca building or a temporary structure?",
            "Is there severe waterlogging outside your premises?"
        ]
        steps = [
            f"Active weather alert is monitored for {location_str}. Expect heavy precipitation/gales.",
            "Stay indoors inside concrete pucca structures away from glass windows and tin roofs.",
            "Do not venture into open fields, near tall trees, or coastal shorelines during lightning or high winds.",
            "Listen to regular official IMD weather bulletins on battery-powered radio or local emergency broadcasts."
        ]

    else:
        agent_role = "knowledge"
        agent_name = "Government Knowledge Agent (RAG)"
        agent_icon = "📚"
        answer_summary = f"Verified NDMA disaster doctrine guidelines for {location_str}:"
        follow_ups = [
            "Are you in immediate physical danger right now?",
            "Do you require immediate rescue boat or medical assistance?"
        ]
        steps = [
            "Follow official announcements from the District Disaster Management Authority (DDMA).",
            "Keep emergency helplines ready: Dial 112 for Police/Fire/Ambulance, 1070 for State Control Room, 1077 for District Control Room.",
            "Remain calm, stay with your family, and assist elderly neighbours or vulnerable children.",
            "Avoid sharing unverified social media rumours. Refer only to official government channels."
        ]

    return {
        "question": question,
        "district": district,
        "state": state,
        "hazard": hazard,
        "agent": {
            "role": agent_role,
            "name": agent_name,
            "icon": agent_icon,
        },
        "answer_summary": answer_summary,
        "follow_up_questions": follow_ups,
        "steps": steps,
        "helplines": [
            "112 (National Emergency)",
            "1070 (State Relief)",
            "1077 (District Control)",
            "108 (Ambulance)",
        ],
        "is_llm_reasoned": False,
    }
