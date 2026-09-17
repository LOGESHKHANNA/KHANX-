import os
import json
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

class ActionStatus:
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDITED = "EDITED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"

class ActionApproval:
    """Represents a structured action proposed by KHANX requiring human approval."""

    def __init__(
        self,
        action_id: str,
        user_id: str,
        session_id: Optional[str],
        action_type: str,
        tool_name: str,
        arguments: Dict[str, Any],
        explanation: str,
        risk_level: str = "HIGH",
        status: str = ActionStatus.PENDING,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        expires_at: Optional[str] = None,
        execution_result: Optional[str] = None
    ):
        now = datetime.now(timezone.utc)
        self.action_id = action_id or f"act_{uuid.uuid4().hex[:12]}"
        self.user_id = user_id
        self.session_id = session_id
        self.action_type = action_type
        self.tool_name = tool_name
        self.arguments = arguments
        self.explanation = explanation
        self.risk_level = risk_level
        self.status = status
        self.created_at = created_at or now.isoformat()
        self.updated_at = updated_at or now.isoformat()
        self.expires_at = expires_at or (now + timedelta(minutes=10)).isoformat()
        self.execution_result = execution_result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "action_type": self.action_type,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "explanation": self.explanation,
            "risk_level": self.risk_level,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "execution_result": self.execution_result,
        }

    def is_expired(self) -> bool:
        try:
            exp_dt = datetime.fromisoformat(self.expires_at)
            return datetime.now(timezone.utc) > exp_dt
        except Exception:
            return False

class ApprovalManager:
    """Manages human-in-the-loop action proposals, approvals, security barriers, and executions."""

    def __init__(self, data_dir: str = "data/approvals"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self._in_memory_actions: Dict[str, ActionApproval] = {}

    def _get_user_filepath(self, user_id: str) -> str:
        safe_user_id = "".join(c for c in user_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self.data_dir, f"{safe_user_id}.json")

    def _load_user_actions(self, user_id: str) -> Dict[str, ActionApproval]:
        path = self._get_user_filepath(user_id)
        actions = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                    for item in raw_list:
                        act = ActionApproval(**item)
                        actions[act.action_id] = act
            except Exception as e:
                print(f"Error loading approvals for {user_id}: {e}")
        return actions

    def _save_user_actions(self, user_id: str, actions: Dict[str, ActionApproval]) -> None:
        path = self._get_user_filepath(user_id)
        try:
            raw_list = [act.to_dict() for act in actions.values()]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw_list, f, indent=2)
        except Exception as e:
            print(f"Error saving approvals for {user_id}: {e}")

    async def propose_action(
        self,
        user_id: str,
        session_id: Optional[str],
        action_type: str,
        tool_name: str,
        arguments: Dict[str, Any],
        explanation: str,
        risk_level: str = "HIGH",
        db: Optional[Any] = None
    ) -> ActionApproval:
        """Create a new action proposal in PENDING status."""
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        proposal = ActionApproval(
            action_id=action_id,
            user_id=user_id,
            session_id=session_id,
            action_type=action_type,
            tool_name=tool_name,
            arguments=arguments,
            explanation=explanation,
            risk_level=risk_level,
            status=ActionStatus.PENDING
        )

        # 1. Supabase persistence if available
        if db:
            try:
                db.table("action_approvals").insert(proposal.to_dict()).execute()
            except Exception:
                pass

        # 2. Local JSON persistence
        user_actions = self._load_user_actions(user_id)
        user_actions[action_id] = proposal
        self._save_user_actions(user_id, user_actions)
        self._in_memory_actions[action_id] = proposal

        return proposal

    async def get_action(self, action_id: str, user_id: str, db: Optional[Any] = None) -> Optional[ActionApproval]:
        """Fetch action proposal by ID ensuring user ownership."""
        if action_id in self._in_memory_actions:
            act = self._in_memory_actions[action_id]
            if act.user_id == user_id:
                return act

        user_actions = self._load_user_actions(user_id)
        if action_id in user_actions:
            act = user_actions[action_id]
            self._in_memory_actions[action_id] = act
            return act

        if db:
            try:
                res = db.table("action_approvals").select("*").eq("action_id", action_id).eq("user_id", user_id).execute()
                if res.data:
                    act = ActionApproval(**res.data[0])
                    self._in_memory_actions[action_id] = act
                    return act
            except Exception:
                pass

        return None

    async def get_pending_actions(self, user_id: str, db: Optional[Any] = None) -> List[Dict[str, Any]]:
        """List active non-expired PENDING action proposals for user."""
        user_actions = self._load_user_actions(user_id)
        pending = []

        for act in user_actions.values():
            if act.status == ActionStatus.PENDING:
                if act.is_expired():
                    act.status = ActionStatus.EXPIRED
                    act.updated_at = datetime.now(timezone.utc).isoformat()
                else:
                    pending.append(act.to_dict())

        self._save_user_actions(user_id, user_actions)
        return pending

    async def approve_action(
        self,
        action_id: str,
        user_id: str,
        modified_arguments: Optional[Dict[str, Any]] = None,
        db: Optional[Any] = None
    ) -> ActionApproval:
        """Approve an action proposal (optionally editing arguments)."""
        action = await self.get_action(action_id, user_id, db=db)
        if not action:
            raise ValueError(f"Action proposal '{action_id}' not found or unauthorized.")

        if action.user_id != user_id:
            raise PermissionError("Unauthorized attempt to modify action approval.")

        if action.is_expired() or action.status == ActionStatus.EXPIRED:
            action.status = ActionStatus.EXPIRED
            raise ValueError("Action proposal has expired and cannot be approved.")

        if action.status not in (ActionStatus.PENDING, ActionStatus.APPROVED, ActionStatus.EDITED):
            raise ValueError(f"Action cannot be approved from state '{action.status}'.")

        now_str = datetime.now(timezone.utc).isoformat()
        if modified_arguments is not None:
            action.arguments = modified_arguments
            action.status = ActionStatus.EDITED
        else:
            action.status = ActionStatus.APPROVED

        action.updated_at = now_str

        # Update persistence
        user_actions = self._load_user_actions(user_id)
        user_actions[action_id] = action
        self._save_user_actions(user_id, user_actions)
        self._in_memory_actions[action_id] = action

        if db:
            try:
                db.table("action_approvals").update({
                    "arguments": action.arguments,
                    "status": action.status,
                    "updated_at": now_str
                }).eq("action_id", action_id).execute()
            except Exception:
                pass

        return action

    async def reject_action(
        self,
        action_id: str,
        user_id: str,
        db: Optional[Any] = None
    ) -> ActionApproval:
        """Reject an action proposal."""
        action = await self.get_action(action_id, user_id, db=db)
        if not action:
            raise ValueError(f"Action proposal '{action_id}' not found or unauthorized.")

        if action.user_id != user_id:
            raise PermissionError("Unauthorized attempt to reject action approval.")

        now_str = datetime.now(timezone.utc).isoformat()
        action.status = ActionStatus.REJECTED
        action.updated_at = now_str

        user_actions = self._load_user_actions(user_id)
        user_actions[action_id] = action
        self._save_user_actions(user_id, user_actions)
        self._in_memory_actions[action_id] = action

        if db:
            try:
                db.table("action_approvals").update({
                    "status": action.status,
                    "updated_at": now_str
                }).eq("action_id", action_id).execute()
            except Exception:
                pass

        return action

    async def execute_approved_action(
        self,
        action_id: str,
        user_id: str,
        db: Optional[Any] = None
    ) -> Dict[str, Any]:
        """Strict backend enforcement check before executing sensitive tool."""
        action = await self.get_action(action_id, user_id, db=db)
        if not action:
            raise ValueError(f"Action proposal '{action_id}' not found.")

        # 1. Authorization check
        if action.user_id != user_id:
            raise PermissionError("Unauthorized attempt to execute action.")

        # 2. Duplicate execution check
        if action.status == ActionStatus.EXECUTED:
            raise ValueError(f"Action '{action_id}' has already been executed (duplicate execution blocked).")

        # 3. Expiration check
        if action.is_expired() or action.status == ActionStatus.EXPIRED:
            action.status = ActionStatus.EXPIRED
            user_actions = self._load_user_actions(user_id)
            user_actions[action_id] = action
            self._save_user_actions(user_id, user_actions)
            raise ValueError(f"Action approval '{action_id}' has expired.")

        # 4. Strict status check: MUST be APPROVED or EDITED
        if action.status not in (ActionStatus.APPROVED, ActionStatus.EDITED):
            raise ValueError(f"Action approval required! Current status is '{action.status}'. Execution refused.")

        # Dispatch execution
        from app.agent.tools.registry import tool_registry
        now_str = datetime.now(timezone.utc).isoformat()

        try:
            exec_result = await tool_registry.execute_tool(
                name=action.tool_name,
                arguments=action.arguments,
                db=db,
                user_id=user_id,
                bypass_hitl=True  # Backend explicit execution after user approval
            )
            action.status = ActionStatus.EXECUTED
            action.execution_result = str(exec_result)
            action.updated_at = now_str
        except Exception as exec_err:
            action.status = ActionStatus.FAILED
            action.execution_result = f"Error during tool execution: {str(exec_err)}"
            action.updated_at = now_str

        # Update persistence
        user_actions = self._load_user_actions(user_id)
        user_actions[action_id] = action
        self._save_user_actions(user_id, user_actions)
        self._in_memory_actions[action_id] = action

        if db:
            try:
                db.table("action_approvals").update({
                    "status": action.status,
                    "execution_result": action.execution_result,
                    "updated_at": now_str
                }).eq("action_id", action_id).execute()
            except Exception:
                pass

        return action.to_dict()

# Global approval manager instance
approval_manager = ApprovalManager()
