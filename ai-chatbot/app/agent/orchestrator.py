import json
import asyncio
from typing import AsyncGenerator, Dict, List, Any, Optional
from app.agent.tools.registry import tool_registry
from app.agent.memory import memory_manager
from app.agent.intent_router import intent_router
from app.agent.response_mode import response_mode_detector
from app.agent.study_mode import study_mode_engine
from app.agent.coding_mode import coding_mode_engine
from app.agent.doc_intelligence import doc_intelligence_engine
from app.agent.research_agent import research_agent
from app.agent.fact_checker import fact_checker
from app.agent.task_planner import task_planner
from app.agent.multi_agent import multi_agent_orchestrator
from app.agent.tracing import agent_tracer
from app.agent.security import security_guard
from app.services.vector_store import get_multi_document_context
from app.core.config import settings
from app.services.groq_retry import call_groq_with_retry
import groq

MAX_TOOL_CALLS = 5

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}

KHANNAX_SYSTEM_PROMPT = """You are KHANNAX, an advanced, highly intelligent conversational AI assistant created by Logesh Khanna. Your answers are clear, direct, comprehensive, useful, and naturally structured.

You have access to modular tools:
1. `search_knowledge_base`: Search uploaded user documents and PDFs for document-specific context.
2. `web_search`: Search the web for current events, recent news, real-time facts, or live updates.
3. `calculator`: Perform mathematical calculations safely.
4. `wikipedia_search`: Search Wikipedia for biographies, concepts, history, and science.
5. `analyze_image`: Analyze uploaded image files, screenshots, diagrams, charts, and handwritten notes.
6. `python_interpreter`: Execute Python code in an isolated sandbox for data analysis, CSV processing, and matrix calculations.
7. `long_term_memory`: Save, recall, or delete user preferences, project context, and session goals across conversations.
8. `manage_tasks`: Create, view, update, complete, or delete personal user tasks through chat.
9. `check_calendar_availability`: Check user's calendar availability and open time slots for a given date.
10. `create_calendar_event`: Schedule or create a new event/meeting on user's calendar (requires user approval).
11. `draft_email`: Draft a new email or prepare a reply for user review (does NOT send).
12. `send_email`: Send a prepared email draft or message (SENSITIVE ACTION: REQUIRES EXPLICIT USER APPROVAL).
13. `generate_image`: Generate an image from a user's text prompt and return it directly.

TOOL CHOICE GUIDELINES:
- For questions about user's uploaded files or documents, use `search_knowledge_base`.
- For questions about recent events, current weather, news, or live information, use `web_search`.
- If a query involves both uploaded documents AND live web facts, you may call `search_knowledge_base` AND `web_search`.
- For managing personal tasks through chat (add, list, update, complete, delete), use `manage_tasks`.
- For checking schedule/availability, use `check_calendar_availability`.
- For scheduling/creating a calendar event, use `create_calendar_event`.
- For drafting an email or preparing a reply, use `draft_email`.
- For proposing to send an email, use `send_email` (which will trigger HITL user approval).
- For requests to generate, create, or draw an image, use `generate_image`.
- For standard general queries, answer directly without tools.
- If `web_search`, calendar, or email tools fail or are unlinked, fall back seamlessly to standard responses without raising errors.

TASK MANAGER GUIDELINES:
- Use `manage_tasks` action='create' when user asks to add/create a task or reminder.
- Use `manage_tasks` action='view' when user asks to view/list tasks (status_filter: 'pending', 'completed', or 'all').
- Use `manage_tasks` action='complete' when user asks to mark a task as done/complete.
- Use `manage_tasks` action='delete' when user asks to delete/remove a task.
- Tasks are strictly private to the authenticated user. Never attempt to access another user's tasks.

CALENDAR INTEGRATION GUIDELINES:
- Use `check_calendar_availability` when user asks "am I free tomorrow?", "check my schedule", or "what's on my calendar?".
- Use `create_calendar_event` when user asks to schedule a meeting or add an event. Creating an event MUST require explicit user approval.
- If the user has not connected a calendar, inform them with the authorization link and continue standard assistance.

EMAIL INTEGRATION GUIDELINES:
- Flow: Draft -> User Approval -> Send. NEVER send emails automatically.
- Use `draft_email` when user asks "draft an email to...", "prepare a reply for...", or "compose an email".
- Use `send_email` when user asks to send a message. Sending MUST require explicit user approval via HITL proposal.
- ZERO CREDENTIAL EXPOSURE: Never request, handle, store, or output raw email passwords, tokens, or credentials. All token management is handled securely by backend OAuth.

LONG-TERM MEMORY GUIDELINES:
- Use `long_term_memory` action='save' to remember important user preferences (e.g. coding language, tone, project name, tech stack) when the user explicitly states them or when they are strongly implied.
- Use `long_term_memory` action='recall' when the user asks "what do you know about me?", "what are my preferences?", or similar.
- NEVER save passwords, API keys, tokens, secrets, or any sensitive credentials.

SOURCE CITATION GUIDELINES:
- When using information from uploaded documents (RAG context), cite the source using available metadata: `[Doc: <filename>, Chunk <index>]` or `[Doc: <filename>]`.
- When using information from web search results, cite the source using the provided title/URL: `[Web: <source/url>]`.
- STRICT NO-HALLUCINATION RULE: NEVER invent, guess, or fabricate page numbers, section numbers, or source links. Only cite source metadata explicitly provided in the retrieved context.
- Keep standard answer generation 100% unchanged when no document or web source is used (e.g., general chat, simple factual questions, math calculations)."""




class AgentOrchestrator:
    """Orchestrates LLM tool decision loop, multi-layer memory retrieval, tool execution, and final SSE streaming response."""

    def __init__(self):
        self.groq_client = groq.Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None

    async def stream_agent_chat(
        self,
        messages_input: List[Dict[str, str]],
        db: Optional[Any] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        mode: str = "chat"
    ) -> AsyncGenerator[str, None]:
        """Memory-guided tool execution loop and final response streaming."""
        if not self.groq_client:
            yield f"data: {json.dumps({'text': 'GROQ_API_KEY not set in environment.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Start Agent Tracing Context
        last_user_query = messages_input[-1].get("content", "") if messages_input else ""
        is_complex = multi_agent_orchestrator.is_complex_query(last_user_query, mode=mode)
        route_name = "multi_agent_swarm" if is_complex else f"{mode}_chat"
        trace_ctx = agent_tracer.start_trace(request_id=session_id, selected_route=route_name)

        # Check if query warrants multi-agent swarm execution
        if is_complex:
            trace_ctx.increment_iterations()
            async for chunk in multi_agent_orchestrator.run_multi_agent_workflow(
                query=last_user_query,
                user_id=user_id,
                db=db,
                session_id=session_id
            ):
                yield chunk
            agent_tracer.end_trace(trace_ctx)
            return

        # 1. Short-Term Memory: sliding window trim
        # If conversation is long enough, auto-summarize older turns and keep recent messages intact.
        summary_context = None
        if memory_manager.short_term.needs_summarization(messages_input, threshold=16):
            try:
                summary_context = memory_manager.short_term.summarize_conversation(
                    messages=messages_input,
                    groq_client=self.groq_client
                )
            except Exception as summ_err:
                print(f"Auto-summarization warning (falling back to sliding window): {summ_err}")
                summary_context = None

        # If summarized, keep last 6 messages; otherwise use standard sliding window
        if summary_context:
            processed_history = memory_manager.short_term.process_messages(
                messages_input[-6:], summary_context=summary_context
            )
        else:
            processed_history = memory_manager.short_term.process_messages(messages_input)

        # 2. Extract current user message for memory retrieval
        last_user_msg = ""
        for m in reversed(messages_input):
            if m.get("role") == "user" and m.get("content"):
                last_user_msg = m["content"]
                break

        # 3. Intent Router — fast pattern-based classification (zero LLM cost)
        detected_intent = None
        if last_user_msg:
            try:
                detected_intent = intent_router.classify(last_user_msg)
                print(f"[IntentRouter] intent={detected_intent.name} confidence={detected_intent.confidence}")
            except Exception as intent_err:
                print(f"[IntentRouter] classification error (ignoring): {intent_err}")

        # 4. Retrieve relevant Memory Context (Semantic + Episodic)
        system_prompt = KHANNAX_SYSTEM_PROMPT
        if user_id and last_user_msg:
            memory_ctx = await memory_manager.get_memory_context(user_id=user_id, query=last_user_msg, db=db)
            if memory_ctx:
                system_prompt += f"\n\n=== RELEVANT AGENT MEMORY ===\n{memory_ctx}\n==========================="

        # Inject routing hint into system prompt for non-general intents
        if detected_intent and detected_intent.name != "general_chat" and detected_intent.confidence >= 0.7:
            system_prompt += (
                f"\n\n[ROUTING HINT] Detected intent: '{detected_intent.name}' "
                f"(confidence: {detected_intent.confidence:.0%}). "
                f"Prioritize using '{detected_intent.suggested_tool}' tool where appropriate."
            )

        # 5. Specialized Engine Detection (Study, Coding, Doc Intelligence, Research Agent, Task Planner)
        study_cfg = study_mode_engine.detect_study_config(last_user_msg, mode_param=mode)
        coding_cfg = coding_mode_engine.detect_coding_config(last_user_msg, mode_param=mode) if not study_cfg else None
        doc_cfg = doc_intelligence_engine.detect_doc_task(last_user_msg, mode_param=mode) if not (study_cfg or coding_cfg) else None
        is_research = research_agent.is_research_query(last_user_msg, mode_param=mode) if not (study_cfg or coding_cfg or doc_cfg) else False
        should_plan = task_planner.should_plan_task(last_user_msg, mode_param=mode) if not (study_cfg or coding_cfg or doc_cfg or is_research) else False

        if study_cfg:
            rag_output = None
            if user_id and last_user_msg:
                try:
                    rag_output = await tool_registry.execute_tool("search_knowledge_base", {"query": last_user_msg}, db=db, user_id=user_id)
                except Exception as rag_err:
                    print(f"Study Mode RAG retrieval warning: {rag_err}")
            study_prompt_overlay = study_mode_engine.build_study_system_prompt(study_cfg, rag_context=rag_output)
            system_prompt += study_prompt_overlay
        elif coding_cfg:
            # 6. Coding Mode Detection
            coding_prompt_overlay = coding_mode_engine.build_coding_system_prompt(coding_cfg)
            system_prompt += coding_prompt_overlay
        elif doc_cfg:
            # 7. Document Intelligence Detection
            multi_doc_ctx = None
            single_rag_ctx = None
            if user_id:
                try:
                    multi_doc_ctx = get_multi_document_context(user_id=user_id, max_chunks_per_doc=8)
                except Exception as multi_doc_err:
                    print(f"Multi-doc context retrieval warning: {multi_doc_err}")
                if not multi_doc_ctx and last_user_msg:
                    try:
                        single_rag_ctx = await tool_registry.execute_tool("search_knowledge_base", {"query": last_user_msg}, db=db, user_id=user_id)
                    except Exception as rag_err:
                        print(f"Doc Intelligence RAG warning: {rag_err}")

            doc_prompt_overlay = doc_intelligence_engine.build_doc_system_prompt(
                doc_cfg,
                multi_doc_context=multi_doc_ctx,
                single_rag_context=single_rag_ctx
            )
            system_prompt += doc_prompt_overlay
        elif is_research:
            # 8. Autonomous Multi-Source Research Agent
            try:
                plan = research_agent.create_research_plan(last_user_msg)
                findings = await research_agent.execute_research(plan, user_id=user_id, db=db)
                research_prompt_overlay = research_agent.build_research_system_prompt(plan, findings)
                system_prompt += research_prompt_overlay
            except Exception as res_err:
                print(f"Research agent warning (falling back to standard chat): {res_err}")
        elif should_plan:
            # 9. Multi-Step Task Planner Engine
            try:
                task_plan = task_planner.create_plan(last_user_msg)
                planner_prompt_overlay = task_planner.build_planner_system_prompt(task_plan)
                system_prompt += planner_prompt_overlay
            except Exception as plan_err:
                print(f"Task planner warning (falling back to standard chat): {plan_err}")
        else:
            # 10. Response Mode Detection (if no specialized engine triggered)
            detected_mode = response_mode_detector.detect(last_user_msg)
            if detected_mode:
                system_prompt += f"\n\n=== RESPONSE MODE: {detected_mode.name.upper()} ===\n{detected_mode.directive}\n=========================================="


        messages = [{"role": "system", "content": system_prompt}]
        for m in processed_history:
            messages.append(m)

        # If mode is explicitly RAG (and not handled by special modes above), automatically search knowledge base
        if mode == "rag" and not (study_cfg or doc_cfg) and user_id and db and last_user_msg:


            rag_output = await tool_registry.execute_tool("search_knowledge_base", {"query": last_user_msg}, db=db, user_id=user_id)
            if rag_output:
                safe_rag_context = security_guard.format_untrusted_context(rag_output, source_name="Uploaded Documents Knowledge Base")
                messages.append({
                    "role": "system",
                    "content": safe_rag_context
                })


        tool_calls_count = 0
        tools_schema = tool_registry.get_schemas()

        try:
            # Tool-calling loop (Max MAX_TOOL_CALLS = 5)
            while tool_calls_count < MAX_TOOL_CALLS:
                trace_ctx.increment_iterations()
                completion = call_groq_with_retry(
                    self.groq_client.chat.completions.create,
                    messages=messages,
                    model="groq/compound-mini",
                    tools=tools_schema,
                    tool_choice="auto",
                    max_tokens=2048,
                )

                if hasattr(completion, "usage") and completion.usage:
                    trace_ctx.record_token_usage(
                        getattr(completion.usage, "prompt_tokens", 0),
                        getattr(completion.usage, "completion_tokens", 0)
                    )

                response_message = completion.choices[0].message

                if hasattr(response_message, "tool_calls") and response_message.tool_calls:
                    assistant_msg = {
                        "role": "assistant",
                        "content": response_message.content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                }
                            }
                            for tc in response_message.tool_calls
                        ]
                    }
                    messages.append(assistant_msg)

                    for tool_call in response_message.tool_calls:
                        tool_calls_count += 1
                        func_name = tool_call.function.name
                        try:
                            func_args = json.loads(tool_call.function.arguments) if isinstance(tool_call.function.arguments, str) else tool_call.function.arguments
                        except Exception:
                            func_args = {}

                        tool_result = await tool_registry.execute_tool(
                            name=func_name,
                            arguments=func_args,
                            db=db,
                            user_id=user_id,
                            session_id=session_id
                        )

                        tool_str = str(tool_result)
                        if tool_str.startswith("[ACTION_APPROVAL_REQUIRED:"):
                            # Yield approval payload directly to client and end stream
                            yield f"data: {json.dumps({'text': tool_str})}\n\n"
                            yield "data: [DONE]\n\n"
                            return

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": tool_str,
                        })

                        if tool_calls_count >= MAX_TOOL_CALLS:
                            break
                else:
                    break

        except Exception as tool_loop_err:
            print(f"Agent tool loop error / fallback triggered: {tool_loop_err}")

        # Stream final answer
        full_assistant_response = ""
        try:
            stream = call_groq_with_retry(
                self.groq_client.chat.completions.create,
                messages=messages,
                model="groq/compound-mini",
                max_tokens=2048,
                stream=True,
            )

            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    safe_delta = security_guard.sanitize_model_output(delta)
                    full_assistant_response += safe_delta
                    yield f"data: {json.dumps({'text': safe_delta})}\n\n"

            # Optional Fact-Checking step for research-heavy queries
            if fact_checker.should_fact_check(last_user_msg, context=system_prompt, mode_param=mode):
                try:
                    fact_res = fact_checker.verify_claims(full_assistant_response, source_context=system_prompt)
                    if fact_res.is_research_heavy and fact_res.unsupported_claims and fact_res.qualified_response:
                        qual_diff = fact_res.qualified_response[len(full_assistant_response):]
                        if qual_diff:
                            yield f"data: {json.dumps({'text': qual_diff})}\n\n"
                            full_assistant_response = fact_res.qualified_response
                except Exception as fc_err:
                    print(f"Fact-checking verification warning: {fc_err}")

        except Exception as stream_err:
            trace_ctx.record_error(str(stream_err))
            yield f"data: {json.dumps({'text': f'Error generating response: {str(stream_err)}'})}\n\n"

        # 4. Auto-update Episodic Memory for session continuity if session_id and user_id present
        if user_id and session_id and full_assistant_response and len(messages_input) >= 2:
            try:
                summary_text = f"User discussed '{last_user_msg[:60]}...' Assistant replied: '{full_assistant_response[:100]}...'"
                await memory_manager.episodic.save_session_summary(
                    user_id=user_id,
                    session_id=session_id,
                    summary=summary_text,
                    db=db
                )
            except Exception as ep_err:
                print(f"Episodic memory auto-save warning: {ep_err}")

        agent_tracer.end_trace(trace_ctx)
        yield "data: [DONE]\n\n"

agent_orchestrator = AgentOrchestrator()
