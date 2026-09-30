import uuid

import streamlit as st
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from scenarios import SCENARIOS
from src.graph import build_graph
from src.tools import BOOKINGS

st.set_page_config(
    page_title="Skylink Assist",
    page_icon="✈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Fraunces:opsz,wght@9..144,600;9..144,700&display=swap');

      html, body, [class*="css"] {
        font-family: "DM Sans", sans-serif;
        color: #0b1f33;
      }

      .stApp {
        background:
          radial-gradient(1200px 500px at 10% -10%, #cfe8f7 0%, transparent 55%),
          linear-gradient(180deg, #e8f3fa 0%, #f7fafc 42%, #eef4f8 100%);
      }

      h1, h2, h3 {
        font-family: "Fraunces", Georgia, serif !important;
        letter-spacing: -0.02em;
      }

      .brand {
        font-family: "Fraunces", Georgia, serif;
        font-size: 2.6rem;
        font-weight: 700;
        color: #0b1f33;
        margin: 0 0 0.2rem 0;
      }

      .tagline {
        color: #3d5a73;
        font-size: 1.05rem;
        margin-bottom: 1.2rem;
      }

      .meta-chip {
        display: inline-block;
        background: #0b1f33;
        color: #e8f3fa;
        padding: 0.35rem 0.75rem;
        border-radius: 4px;
        font-size: 0.85rem;
        margin-right: 0.4rem;
        margin-bottom: 0.4rem;
      }

      .meta-chip.ok { background: #0f6b4c; }
      .meta-chip.warn { background: #9a3412; }

      div[data-testid="stChatMessage"] {
        background: rgba(255,255,255,0.72);
        border: 1px solid #d5e4ef;
        border-radius: 12px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_app():
    return build_graph(checkpointer=MemorySaver())


def blank_state(request_id: str, booking_ref: str, message: str) -> dict:
    return {
        "request_id": request_id,
        "booking_ref": booking_ref,
        "messages": [HumanMessage(content=message)],
        "intent": None,
        "constraints": {},
        "active_agent": None,
        "booking": None,
        "proposed_solution": None,
        "policy_passed": None,
        "policy_failure_reason": None,
        "retry_count": 0,
        "escalated": False,
        "escalation_note": None,
        "final_response": None,
        "supervisor_approved": None,
    }


def reset_chat(thread_prefix: str = "ui"):
    st.session_state.thread_id = f"{thread_prefix}-{uuid.uuid4().hex[:8]}"
    st.session_state.chat = []
    st.session_state.last_result = None
    st.session_state.started = False
    st.session_state.last_base_scenario = None
    st.session_state.pending_interrupt = None


def ensure_session():
    defaults = {
        "chat": [],
        "last_result": None,
        "started": False,
        "active_scenario": None,
        "last_base_scenario": None,
        "thread_id": f"ui-{uuid.uuid4().hex[:8]}",
        "pending_interrupt": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def interrupt_payload(result) -> dict | None:
    items = result.get("__interrupt__") if isinstance(result, dict) else None
    if not items:
        return None
    first = items[0]
    return getattr(first, "value", first)


def store_result(result, user_message: str | None = None):
    st.session_state.last_result = result
    if user_message:
        st.session_state.chat.append(("you", user_message))
    payload = interrupt_payload(result)
    if payload:
        st.session_state.pending_interrupt = payload
        st.session_state.chat.append(
            (
                "assist",
                payload.get("message")
                or "Waiting for supervisor approval (payout over $300).",
            )
        )
    else:
        st.session_state.pending_interrupt = None
        st.session_state.chat.append(
            ("assist", result.get("final_response") or "(no reply)")
        )


def run_new_case(scenario: dict):
    reset_chat(thread_prefix=scenario["booking_ref"])
    st.session_state.active_scenario = scenario["id"]
    st.session_state.last_base_scenario = scenario["id"]
    app = get_app()
    result = app.invoke(
        blank_state(scenario["request_id"], scenario["booking_ref"], scenario["message"]),
        config={"configurable": {"thread_id": st.session_state.thread_id}},
    )
    st.session_state.started = True
    store_result(result, scenario["message"])


def run_follow_up(scenario: dict):
    required = scenario.get("requires")
    if required and st.session_state.last_base_scenario != required:
        st.warning(f"Run Scenario {required} first, then this follow-up.")
        return
    if not st.session_state.started:
        st.warning("Start a scenario first before sending a follow-up.")
        return
    if st.session_state.pending_interrupt:
        st.warning("Approve or reject the pending supervisor request first.")
        return
    st.session_state.active_scenario = scenario["id"]
    app = get_app()
    result = app.invoke(
        {"messages": [HumanMessage(content=scenario["message"])]},
        config={"configurable": {"thread_id": st.session_state.thread_id}},
    )
    store_result(result, scenario["message"])


def resume_supervisor(approved: bool):
    app = get_app()
    result = app.invoke(
        Command(resume={"approved": approved}),
        config={"configurable": {"thread_id": st.session_state.thread_id}},
    )
    store_result(result)


ensure_session()

st.markdown('<p class="brand">Skylink Assist</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="tagline">Pick a scenario — booking and message are filled for you.</p>',
    unsafe_allow_html=True,
)

st.subheader("Scenarios")
for scenario in SCENARIOS:
    booking = BOOKINGS[scenario["booking_ref"]]
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"**{scenario['id']}. {scenario['title']}**")
            st.caption(scenario["expected_path"])
            st.write(
                f"`{scenario['booking_ref']}` · {booking['passenger_name']} · "
                f"{booking['origin']}→{booking['destination']} · {booking['status']}"
            )
            st.write(f"_{scenario['message']}_")
            st.caption(scenario["notes"])
        with c2:
            if st.button("Run", key=f"run-{scenario['id']}", use_container_width=True):
                with st.spinner("Running scenario…"):
                    try:
                        if scenario.get("follow_up"):
                            run_follow_up(scenario)
                        else:
                            run_new_case(scenario)
                    except Exception as exc:
                        st.error(f"Failed: {exc}")
                    else:
                        st.rerun()

st.divider()

result = st.session_state.last_result
pending = st.session_state.pending_interrupt

if st.session_state.active_scenario:
    st.caption(
        f"Active scenario: {st.session_state.active_scenario} · thread `{st.session_state.thread_id}`"
    )

if pending:
    st.warning("Human-in-the-loop: supervisor approval required")
    st.write(pending.get("message"))
    st.json(
        {
            "payout_type": pending.get("payout_type"),
            "amount": pending.get("amount"),
            "threshold": pending.get("threshold"),
            "booking_ref": pending.get("booking_ref"),
        }
    )
    a1, a2 = st.columns(2)
    with a1:
        if st.button("Approve payout", type="primary", use_container_width=True):
            with st.spinner("Resuming graph…"):
                resume_supervisor(True)
                st.rerun()
    with a2:
        if st.button("Reject payout", use_container_width=True):
            with st.spinner("Resuming graph…"):
                resume_supervisor(False)
                st.rerun()

if result and not pending:
    chips = [f'<span class="meta-chip">intent: {result.get("intent")}</span>']
    if result.get("policy_passed"):
        chips.append('<span class="meta-chip ok">policy: pass</span>')
    elif result.get("policy_passed") is False:
        chips.append('<span class="meta-chip warn">policy: fail</span>')
    if result.get("supervisor_approved") is True:
        chips.append('<span class="meta-chip ok">supervisor: approved</span>')
    elif result.get("supervisor_approved") is False:
        chips.append('<span class="meta-chip warn">supervisor: rejected</span>')
    if result.get("escalated"):
        chips.append('<span class="meta-chip warn">escalated</span>')
    chips.append(f'<span class="meta-chip">retries: {result.get("retry_count", 0)}</span>')
    st.markdown("".join(chips), unsafe_allow_html=True)

left, right = st.columns([1.4, 1])

with left:
    st.subheader("Conversation")
    if not st.session_state.chat:
        st.info("Choose a scenario above and click Run.")
    for role, text in st.session_state.chat:
        with st.chat_message("user" if role == "you" else "assistant"):
            st.write(text)

    prompt = st.chat_input("Optional follow-up on the same thread…")
    if prompt:
        with st.spinner("Sending follow-up…"):
            try:
                run_follow_up(
                    {
                        "id": "custom",
                        "message": prompt,
                        "requires": None,
                    }
                )
            except Exception as exc:
                st.error(f"Failed: {exc}")
            else:
                st.rerun()

with right:
    st.subheader("Case details")
    if not result:
        st.info("Results appear here after you run a scenario.")
    else:
        st.markdown("**Proposed solution**")
        st.json(result.get("proposed_solution") or {})
        if result.get("policy_failure_reason"):
            st.warning(result["policy_failure_reason"])
        if result.get("escalation_note"):
            st.markdown("**Escalation note**")
            st.write(result["escalation_note"])
        st.markdown("**Booking**")
        st.json(result.get("booking") or {})

with st.sidebar:
    st.markdown("### How to use")
    st.write(
        "1. Click **Run** on a scenario\n"
        "2. If payout is over $300, approve or reject\n"
        "3. For refund follow-up: run **1**, then **1b**\n"
        "4. Or type a custom follow-up in chat"
    )
    st.caption("HITL: refund/compensation over $300 pauses with interrupt().")
    if st.button("Clear conversation", use_container_width=True):
        reset_chat()
        st.session_state.active_scenario = None
        st.session_state.last_base_scenario = None
        st.rerun()
