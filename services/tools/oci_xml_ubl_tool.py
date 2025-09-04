"""
Herramienta especializada para procesamiento de XML UBL (Universal Business Language)
Maneja AttachedDocument e Invoice según estándares DIAN y UBL 2.1.
Devuelve el CONTENIDO que correspondería a <base>__FLAT_FULL.json como *string*
(aunque aquí trabajamos en memoria con dict {filename: xml_content}).
"""

import json
import logging
import re
from typing import Dict, Any, Optional

from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)


class OCIXMLUBLTool:
    """
    Procesa XML UBL (AttachedDocument + Invoice embebido en CDATA).
    Entrada: (filename, files_dict) donde files_dict = {filename: xml_content_str}
    Salida: string JSON con:
      {
        "attached_flat": {...},   # contenido aplanado del contenedor (AttachedDocument)
        "invoice_flat": {...}     # (opcional) factura UBL aplanada si es encontrada
      }
    """

    # ------------------------ utilidades internas ------------------------

    @staticmethod
    def _localname(tag: str) -> str:
        """Nombre local del tag sin namespace."""
        if "}" in tag:
            return tag.split("}", 1)[1]
        return tag

    def _elem_to_dict(self, elem: ET.Element) -> Any:
        """
        Convierte un Element en estructura dict:
        - Atributos con prefijo '@'
        - Texto en '#text'
        - Hijos agrupados por tag; repetidos → lista
        """
        node: Dict[str, Any] = {}

        # Atributos
        for k, v in elem.attrib.items():
            node[f"@{self._localname(k)}"] = v

        # Hijos
        children = list(elem)
        if children:
            group: Dict[str, Any] = {}
            for child in children:
                key = self._localname(child.tag)
                child_dict = self._elem_to_dict(child)
                group.setdefault(key, []).append(child_dict)
            for k, v in group.items():
                node[k] = v if len(v) > 1 else v[0]

        # Texto
        text = (elem.text or "").strip()
        if text:
            if node:
                node["#text"] = text
            else:
                # Nodo hoja
                return text

        return node

    def _flatten_dict(self, d: Any, prefix: str = "", sep: str = ".") -> Dict[str, Any]:
        """
        Aplana dict/list a un solo nivel con claves punteadas.
        Listas con índices: key[0].subkey
        """
        flat: Dict[str, Any] = {}
        if isinstance(d, dict):
            for k, v in d.items():
                key = f"{prefix}{sep}{k}" if prefix else k
                flat.update(self._flatten_dict(v, key, sep))
        elif isinstance(d, list):
            for i, v in enumerate(d):
                key = f"{prefix}[{i}]"
                flat.update(self._flatten_dict(v, key, sep))
        else:
            flat[prefix] = d
        return flat

    def _find_embedded_invoice_xml(self, root: ET.Element) -> Optional[str]:
        """
        En AttachedDocument, el Invoice embebido suele estar en:
          /cac:Attachment/cac:ExternalReference/cbc:Description (CDATA)
        Retorna el XML interno (string) si se encuentra; si no, None.
        """
        for desc in root.iter():
            if self._localname(desc.tag) == "Description":
                t = (desc.text or "").strip()
                if t.startswith("<") and ("<Invoice" in t or "<ns2:Invoice" in t or "<inv:Invoice" in t):
                    return t
        return None

    def _parse_lenient(self, xml_text: str) -> ET.Element:
        """Parseo tolerante para CDATA con BOM o entidades raras."""
        try:
            return ET.fromstring(xml_text.encode("utf-8"))
        except Exception:
            inner_clean = xml_text.strip()
            inner_clean = re.sub(r"^[\ufeff]+", "", inner_clean)  # BOM
            return ET.fromstring(inner_clean.encode("utf-8"))

    # ------------------------ API pública ------------------------

    def process_ubl_xml(self, filename: str, files_dict: Dict[str, str]) -> str:
        """
        Procesa el XML indicado por `filename`, tomando el contenido desde `files_dict[filename]`.
        Devuelve el CONTENIDO equivalente a <base>__FLAT_FULL.json como string.
        """
        if filename not in files_dict:
            msg = f"filename '{filename}' no encontrado en files_dict"
            logger.error("[XML-UBL] %s", msg)
            return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)

        xml_content = files_dict[filename]
        if not isinstance(xml_content, str) or not xml_content.strip():
            msg = f"xml_content inválido para '{filename}'"
            logger.error("[XML-UBL] %s", msg)
            return json.dumps({"ok": False, "error": msg}, ensure_ascii=False)

        try:
            # Parseo del contenedor (AttachedDocument u otros)
            root = ET.fromstring(xml_content.encode("utf-8"))
            container_dict = self._elem_to_dict(root)
            flat_container = self._flatten_dict(container_dict, prefix="attached")

            # Intentar localizar Invoice embebido (CDATA en Description)
            inner = self._find_embedded_invoice_xml(root)
            payload: Dict[str, Any] = {"attached_flat": flat_container}

            if inner:
                try:
                    invoice_root = self._parse_lenient(inner)
                    invoice_dict = self._elem_to_dict(invoice_root)
                    flat_invoice = self._flatten_dict(invoice_dict, prefix="invoice")
                    payload["invoice_flat"] = flat_invoice
                except Exception as e:
                    logger.warning("[XML-UBL] No fue posible parsear Invoice interno: %s", e)

            # → Esto es lo que correspondería al contenido de <base>__FLAT_FULL.json
            return json.dumps(payload, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.exception("[XML-UBL] Error procesando '%s': %s", filename, e)
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
