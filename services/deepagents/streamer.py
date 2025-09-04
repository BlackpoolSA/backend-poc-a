# streamer.py (Versión mejorada)

from typing import AsyncGenerator, Dict, Any, List
import logging
# Asegúrate de que los imports apunten a tu proyecto
from deepagents.state import DeepAgentState, Todo
from langgraph.pregel import Pregel
from utils.utils import Utils

class AgentStreamer:
    """
    Encapsula la lógica para hacer streaming del estado de un Deep Agent,
    reutilizando las clases de estado definidas para robustez y mantenibilidad.
    """
    def __init__(self, agent_instance: Pregel):
        self.agent_instance = agent_instance
        self.current_state: DeepAgentState = {
            "messages": [],
            "todos": [],
            "files": {}
        }
        # Campo auxiliar para mensajes de herramientas (serializable)
        self.tool_messages: List[Dict[str, Any]] = []
        self.logger = logging.getLogger(__name__)

    def _normalize_tool_calls(self, calls: Any) -> List[Dict[str, Any]]:
        import json as _json
        normalized: List[Dict[str, Any]] = []
        try:
            try:
                self.logger.info(
                    "[DEEP_AGENT][STREAM][normalize] incoming calls type=%s len=%s",
                    type(calls).__name__,
                    len(calls) if hasattr(calls, "__len__") else "n/a",
                )
            except Exception:
                pass
            for idx, c in enumerate(calls or []):
                try:
                    if isinstance(c, dict):
                        func = (c.get("function") or {}) if isinstance(c.get("function"), dict) else {}
                        raw_args = c.get("args") or func.get("arguments") or c.get("input") or {}
                        if isinstance(raw_args, str):
                            try:
                                raw_args = _json.loads(raw_args)
                            except Exception:
                                pass
                        raw_result = c.get("result") or c.get("output") or c.get("return") or c.get("content")
                        norm = {
                            "id": c.get("id") or c.get("tool_call_id") or "",
                            "name": c.get("name") or func.get("name") or c.get("type") or "tool",
                            "args": raw_args,
                            "type": c.get("type") or ("function" if func else None),
                            "result": raw_result,
                            "status": c.get("status"),
                        }
                        normalized.append(norm)
                        try:
                            self.logger.info(
                                "[DEEP_AGENT][STREAM][normalize] item[%d] id=%s name=%s has_args=%s has_result=%s",
                                idx,
                                str(norm.get("id"))[:36],
                                str(norm.get("name"))[:36],
                                bool(norm.get("args")),
                                bool(norm.get("result")),
                            )
                        except Exception:
                            pass
                    else:
                        func = getattr(c, "function", None)
                        raw_args = (
                            getattr(c, "args", None)
                            or (getattr(func, "arguments", None) if func is not None else None)
                            or getattr(c, "input", None)
                            or {}
                        )
                        if isinstance(raw_args, str):
                            try:
                                raw_args = _json.loads(raw_args)
                            except Exception:
                                pass
                        raw_result = (
                            getattr(c, "result", None)
                            or getattr(c, "output", None)
                            or getattr(c, "return", None)
                            or getattr(c, "content", None)
                        )
                        name_attr = (
                            getattr(c, "name", None)
                            or (getattr(func, "name", None) if func is not None else None)
                            or getattr(c, "type", None)
                            or "tool"
                        )
                        norm = {
                            "id": getattr(c, "id", None) or getattr(c, "tool_call_id", None) or "",
                            "name": name_attr,
                            "args": raw_args,
                            "type": getattr(c, "type", None) or ("function" if func is not None else None),
                            "result": raw_result,
                            "status": getattr(c, "status", None),
                        }
                        normalized.append(norm)
                        try:
                            self.logger.info(
                                "[DEEP_AGENT][STREAM][normalize] item[%d] id=%s name=%s has_args=%s has_result=%s",
                                idx,
                                str(norm.get("id"))[:36],
                                str(norm.get("name"))[:36],
                                bool(norm.get("args")),
                                bool(norm.get("result")),
                            )
                        except Exception:
                            pass
                except Exception as _e:
                    try:
                        self.logger.warning("[DEEP_AGENT][STREAM][normalize] error on item %d: %s", idx, str(_e))
                    except Exception:
                        pass
        except Exception as e:
            try:
                self.logger.warning("[DEEP_AGENT][STREAM][normalize] failure: %s", str(e))
            except Exception:
                pass
        return normalized

    def _serialize_ai_message(self, m: Any) -> Dict[str, Any]:
        content = None
        add_kwargs = {}
        resp_meta = {}
        tool_calls = []
        refusal = None
        try:
            content = getattr(m, "content", None)
        except Exception:
            try:
                content = m.get("content") if isinstance(m, dict) else None
            except Exception:
                content = None
        try:
            add_kwargs = getattr(m, "additional_kwargs", {}) or {}
            refusal = add_kwargs.get("refusal")
            if add_kwargs.get("tool_calls"):
                try:
                    self.logger.info("[DEEP_AGENT][STREAM][ai] additional_kwargs.tool_calls present")
                except Exception:
                    pass
                tool_calls = self._normalize_tool_calls(add_kwargs.get("tool_calls"))
        except Exception as e:
            try:
                self.logger.warning("[DEEP_AGENT][STREAM][ai] add_kwargs parse error: %s", str(e))
            except Exception:
                pass
        try:
            resp_meta = getattr(m, "response_metadata", {}) or {}
        except Exception:
            try:
                resp_meta = m.get("response_metadata") if isinstance(m, dict) else {}
            except Exception:
                resp_meta = {}
        try:
            direct_tool_calls = getattr(m, "tool_calls", None)
            if direct_tool_calls:
                try:
                    self.logger.info("[DEEP_AGENT][STREAM][ai] direct tool_calls present")
                except Exception:
                    pass
                tool_calls = self._normalize_tool_calls(direct_tool_calls)
        except Exception as e:
            try:
                self.logger.warning("[DEEP_AGENT][STREAM][ai] direct tool_calls parse error: %s", str(e))
            except Exception:
                pass
        try:
            usage_meta = getattr(m, "usage_metadata", None)
            if usage_meta and isinstance(usage_meta, dict):
                # fusionar con token_usage si existe
                token_usage = resp_meta.get("token_usage") or {}
                token_usage.update(usage_meta)
                resp_meta["token_usage"] = token_usage
        except Exception:
            pass
        
        return {
            "id": getattr(m, "id", None) if not isinstance(m, dict) else m.get("id"),
            "type": "ai",
            "content": content,
            "tool_calls": tool_calls,
            "refusal": refusal,
            "response_metadata": resp_meta,
        }

    def _serialize_tool_message(self, msg: Any) -> Dict[str, Any]:
        try:
            ser = {
                "content": getattr(msg, "content", None),
                "name": getattr(msg, "name", None),
                "id": getattr(msg, "id", None),
                "tool_call_id": getattr(msg, "tool_call_id", None),
            }
        except Exception:
            try:
                ser = {
                    "content": msg.get("content"),
                    "name": msg.get("name"),
                    "id": msg.get("id"),
                    "tool_call_id": msg.get("tool_call_id"),
                }
            except Exception:
                ser = {"content": str(msg)}
        try:
            self.logger.info(
                "[DEEP_AGENT][STREAM][tool_msg] name=%s tool_call_id=%s has_content=%s",
                str(ser.get("name"))[:36],
                str(ser.get("tool_call_id"))[:36],
                bool(ser.get("content")),
            )
        except Exception:
            pass
        return ser

    def _update_state(self, chunk: Dict[str, Any]):
        """
        Actualiza el estado actual con los datos de un nuevo chunk del stream.
        """
        try:
            self.logger.info(f"[DEEP_AGENT][STREAM] Chunk received keys=%s", list((chunk or {}).keys()))
        except Exception:
            pass

        # Caso 1: frames con 'values' (estado parcial del grafo)
        if isinstance(chunk, dict) and "values" in chunk:
            v = chunk.get("values") or {}
            if isinstance(v, dict):
                if "messages" in v:
                    self.current_state["messages"] = v.get("messages") or []
                if "todos" in v:
                    self.current_state["todos"] = v.get("todos") or []
                if "files" in v:
                    self.current_state["files"] = v.get("files") or {}
            return

        # Caso 2: eventos de herramientas
        if isinstance(chunk, dict) and "tools" in chunk:
            tools_obj = chunk.get("tools", {}) or {}
            todos = tools_obj.get("todos")
            if todos is not None:
                self.current_state["todos"] = todos
            msgs = tools_obj.get("messages") or []
            if msgs:
                serialized = [self._serialize_tool_message(m) for m in msgs]
                # Guardar para inspección/compatibilidad
                self.tool_messages.extend(serialized)
                try:
                    self.logger.info(
                        "[DEEP_AGENT][STREAM] Tool messages appended count=%d total=%d",
                        len(serialized),
                        len(self.tool_messages),
                    )
                except Exception:
                    pass
                # Además, anexar estos mensajes como mensajes de tipo 'tool' para que el frontend
                # pueda enlazarlos por tool_call_id con los tool_calls del último AIMessage
                for sm in serialized:
                    try:
                        tool_msg = {
                            "id": sm.get("id"),
                            "type": "tool",
                            "content": sm.get("content"),
                            "name": sm.get("name"),
                            "tool_call_id": sm.get("tool_call_id"),
                        }
                        existing = self.current_state.get("messages") or []
                        existing.append(tool_msg)
                        self.current_state["messages"] = existing
                        # Intentar mapear el resultado al último AIMessage por tool_call_id
                        try:
                            last_ai_index = None
                            for i in range(len(existing) - 1, -1, -1):
                                if isinstance(existing[i], dict) and existing[i].get("type") == "ai":
                                    last_ai_index = i
                                    break
                            if last_ai_index is not None:
                                ai_msg = existing[last_ai_index]
                                ai_tool_calls = ai_msg.get("tool_calls") or []
                                mapped = False
                                for tc in ai_tool_calls:
                                    if str(tc.get("id") or "") == str(sm.get("tool_call_id") or ""):
                                        tc["result"] = sm.get("content")
                                        tc["status"] = tc.get("status") or "completed"
                                        mapped = True
                                        break
                                if mapped:
                                    existing[last_ai_index]["tool_calls"] = ai_tool_calls
                                    self.current_state["messages"] = existing
                                    try:
                                        self.logger.info(
                                            "[DEEP_AGENT][STREAM] Mapped tool result to AI tool_call id=%s",
                                            str(sm.get("tool_call_id"))[:36],
                                        )
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        # Heurística: actualizar self.current_state["files"] con base en la tool ejecutada
                        try:
                            files_state = self.current_state.get("files") or {}
                            # Buscar los args del tool_call correspondiente en el último AI message
                            last_ai_index = None
                            for i in range(len(existing) - 1, -1, -1):
                                if isinstance(existing[i], dict) and existing[i].get("type") == "ai":
                                    last_ai_index = i
                                    break
                            tool_args = None
                            if last_ai_index is not None:
                                ai_msg = existing[last_ai_index]
                                for tc in (ai_msg.get("tool_calls") or []):
                                    if str(tc.get("id") or "") == str(sm.get("tool_call_id") or ""):
                                        tool_args = tc.get("args") or {}
                                        break
                            tool_name = (sm.get("name") or "").lower()
                            if tool_name == "read_file" and tool_args and sm.get("content"):
                                fp = tool_args.get("file_path") or tool_args.get("path")
                                if isinstance(fp, str) and fp:
                                    files_state[fp] = str(sm.get("content"))
                            elif tool_name == "write_file" and tool_args:
                                fp = tool_args.get("file_path") or tool_args.get("path")
                                content = tool_args.get("content")
                                if isinstance(fp, str) and fp and content is not None:
                                    files_state[fp] = str(content)
                            elif tool_name == "edit_file" and tool_args:
                                fp = tool_args.get("file_path") or tool_args.get("path")
                                new_str = tool_args.get("new_string") or tool_args.get("newContent")
                                if isinstance(fp, str) and fp and new_str is not None:
                                    files_state[fp] = str(new_str)
                            elif tool_name == "ls" and sm.get("content"):
                                # Si ls devuelve listado JSON, no sobrescribir, solo dejar rastro mínimo
                                try:
                                    import json as _json
                                    arr = _json.loads(str(sm.get("content")))
                                    if isinstance(arr, list):
                                        for fname in arr:
                                            if isinstance(fname, str) and fname:
                                                files_state.setdefault(fname, "listed")
                                except Exception:
                                    pass
                            self.current_state["files"] = files_state
                        except Exception:
                            pass
                    except Exception:
                        pass
            return

        # Caso 3: eventos del agente (AIMessage)
        if isinstance(chunk, dict) and "agent" in chunk:
            agent_obj = chunk.get("agent", {}) or {}
            ai_messages = agent_obj.get("messages") or []
            if ai_messages:
                serial = [self._serialize_ai_message(m) for m in ai_messages]
                # En lugar de reemplazar, acumulamos el último AIMessage para no perder mensajes de tool previos
                existing = self.current_state.get("messages") or []
                # Evitar duplicados si el mismo id ya está presente al final
                last_ai = serial[-1]
                if not (existing and isinstance(existing[-1], dict) and existing[-1].get("id") == last_ai.get("id")):
                    existing.append(last_ai)
                self.current_state["messages"] = existing
                try:
                    self.logger.info(
                        "[DEEP_AGENT][STREAM] AI message appended. messages_len=%d",
                        len(existing),
                    )
                except Exception:
                    pass
            return

        # Caso 4: fallback genérico
        if isinstance(chunk, dict):
            if "messages" in chunk:
                self.current_state["messages"] = chunk.get("messages") or []
            if "todos" in chunk:
                self.current_state["todos"] = chunk.get("todos") or []
            if "files" in chunk:
                self.current_state["files"] = chunk.get("files") or {}

    async def stream(self, agent_input: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Inicia el streaming del agente, actualiza el estado y produce
        chunks formateados para el frontend.
        """
        async for chunk in self.agent_instance.astream(agent_input):
            self._update_state(chunk)

            # Emitir sólo si hay algo útil que mostrar
            has_messages = bool(self.current_state.get("messages"))
            has_todos = bool(self.current_state.get("todos"))
            has_files = bool(self.current_state.get("files"))
            if not (has_messages or has_todos or has_files or self.tool_messages):
                continue

            try:
                self.logger.info(
                    "[DEEP_AGENT][STREAM] Emitting values: messages=%d todos=%d files=%d tool_msgs=%d",
                    len(self.current_state.get("messages") or []),
                    len(self.current_state.get("todos") or []),
                    len(self.current_state.get("files") or {}),
                    len(self.tool_messages),
                )
            except Exception:
                pass

            yield {
                "values": {
                    **self.current_state,
                    # Adjuntar tool_messages como campo auxiliar
                    "tool_messages": list(self.tool_messages),
                }
            }

        
        # Evento final: obtener el último content desde el estado consolidado y devolver solo ese string
        final_json = {
            **self.current_state,
            "tool_messages": list(self.tool_messages),
        }


        last_content = ""
        messages = final_json.get("messages") or []
        if isinstance(messages, list):
            for m in reversed(messages):
                if isinstance(m, dict) and m.get("content"):
                    raw = str(m.get("content") or "")
                    last_content = Utils.extract_json_from_text(raw)
                    break
        yield {
            "type": "json",
            "output": last_content
        }