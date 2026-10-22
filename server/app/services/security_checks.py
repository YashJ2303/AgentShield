import os
import re
import urllib.parse
from typing import Optional, Tuple, Any
import sqlglot
import sqlglot.expressions as exp


def _eval_literal(lit: exp.Literal) -> Any:
    val = lit.this
    try:
        if lit.is_number:
            return float(val) if "." in str(val) else int(val)
    except Exception:
        pass
    return str(val)


def _is_tautology(expression: exp.Expression) -> bool:
    """
    Detect tautological WHERE conditions like 1=1, 'a'='a', TRUE, 1<2, id=5 OR 1=1, id IS NOT NULL.
    Note: General SQL tautology detection is equivalent to Boolean Satisfiability (SAT)
    and is NP-complete / undecidable in the general case. This implementation is a best-effort
    AST heuristic defense-in-depth against common bypass techniques.
    """
    if isinstance(expression, exp.Boolean) and expression.this:
        return True

    if isinstance(expression, exp.Literal):
        val = str(expression.this).lower()
        if val in ("1", "true"):
            return True

    # Check for dummy `col IS NOT NULL`
    if isinstance(expression, exp.Not):
        inner = expression.this
        if isinstance(inner, exp.Is) and isinstance(inner.expression, exp.Null):
            return True

    # Check comparison operations between literals
    if isinstance(expression, (exp.EQ, exp.NEQ, exp.LT, exp.LTE, exp.GT, exp.GTE)):
        left = expression.left
        right = expression.right
        if isinstance(left, exp.Literal) and isinstance(right, exp.Literal):
            lv = _eval_literal(left)
            rv = _eval_literal(right)
            try:
                if isinstance(expression, exp.EQ) and lv == rv:
                    return True
                if isinstance(expression, exp.NEQ) and lv != rv:
                    return True
                if isinstance(expression, exp.LT) and lv < rv:
                    return True
                if isinstance(expression, exp.LTE) and lv <= rv:
                    return True
                if isinstance(expression, exp.GT) and lv > rv:
                    return True
                if isinstance(expression, exp.GTE) and lv >= rv:
                    return True
            except TypeError:
                pass

    # Check OR conditions: if any branch is a tautology, the OR condition is a tautology
    if isinstance(expression, exp.Or):
        if _is_tautology(expression.left) or _is_tautology(expression.right):
            return True

    return False


DEFAULT_BLOCKED_OPS = [
    "DROP", "TRUNCATE", "ALTER", "ATTACH", "PRAGMA", "REPLACE",
    "VACUUM", "CREATE", "GRANT", "REVOKE"
]


def check_sql_safety(
    query: str,
    allowed_operations: Optional[list[str]] = None,
    blocked_operations: Optional[list[str]] = None,
    require_where_clause_on: Optional[list[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates SQL safety using sqlglot AST parsing.
    Defaults to SELECT-only unless allowed_operations explicitly permits more.
    Blocks ATTACH, PRAGMA, REPLACE, VACUUM INTO, CREATE, GRANT, REVOKE, DROP, TRUNCATE, ALTER.
    Checks for:
    - Multi-statement injections
    - Blocked operations
    - Unpermitted operation types (outside allowed_operations)
    - Unrestricted DELETE / UPDATE (missing WHERE or tautological WHERE)
    - Unparseable SQL (fail closed)
    """
    if not query or not isinstance(query, str):
        return False, "Empty or non-string SQL query"

    allowed_ops = [op.upper() for op in (allowed_operations or ["SELECT"])]
    blocked_ops = [op.upper() for op in (blocked_operations or DEFAULT_BLOCKED_OPS)]
    require_where = [op.upper() for op in (require_where_clause_on or ["DELETE", "UPDATE"])]

    # Try standard parse first; fallback to sqlite dialect if syntax is dialect-specific
    statements = None
    parse_error = None
    for dialect in [None, "sqlite"]:
        try:
            parsed = sqlglot.parse(query, read=dialect)
            if parsed and any(s is not None for s in parsed):
                statements = parsed
                break
        except Exception as e:
            parse_error = str(e)

    if not statements or all(s is None for s in statements):
        return False, f"SQL syntax error / unparseable query: {parse_error or 'no statements found'}"

    # Blocked AST types
    blocked_types = [
        exp.Drop,
        exp.TruncateTable,
        exp.Alter,
        exp.Create,
        exp.Grant,
    ]
    if hasattr(exp, "Attach"):
        blocked_types.append(exp.Attach)
    if hasattr(exp, "Pragma"):
        blocked_types.append(exp.Pragma)
    if hasattr(exp, "Revoke"):
        blocked_types.append(exp.Revoke)
    blocked_types_tuple = tuple(blocked_types)

    # Phase 1: Check for any blocked operations across all statements
    for stmt in statements:
        if stmt is None or isinstance(stmt, getattr(exp, "Semicolon", tuple())):
            continue
        for node in stmt.walk():
            if isinstance(node, blocked_types_tuple):
                op_label = node.key.upper() if hasattr(node, "key") else type(node).__name__.upper()
                return False, f"Blocked SQL operation detected: {op_label}"
            if isinstance(node, exp.Command):
                cmd_name = str(node.this).upper() if hasattr(node, "this") else ""
                for b in blocked_ops:
                    if b in cmd_name or cmd_name.startswith(b):
                        return False, f"Blocked SQL command detected: {cmd_name}"

    # Phase 2: Check allowed operations and WHERE clause constraints
    for stmt in statements:
        if stmt is None or isinstance(stmt, getattr(exp, "Semicolon", tuple())):
            continue

        # Resolve operation type for permission checking
        if isinstance(stmt, exp.Select):
            op_name = "SELECT"
        elif isinstance(stmt, exp.Insert):
            op_name = "INSERT"
        elif isinstance(stmt, exp.Update):
            op_name = "UPDATE"
        elif isinstance(stmt, exp.Delete):
            op_name = "DELETE"
        elif isinstance(stmt, exp.Command):
            op_name = str(stmt.this).upper()
        else:
            op_name = stmt.key.upper() if hasattr(stmt, "key") else type(stmt).__name__.upper()

        # Check against blocked_ops
        if op_name in blocked_ops:
            return False, f"Blocked SQL operation detected: {op_name}"

        # Check against allowed_operations (defaults to SELECT-only)
        if "*" not in allowed_ops and op_name not in allowed_ops:
            return False, f"SQL operation '{op_name}' is not permitted by policy (allowed operations: {allowed_ops})"

        # Check WHERE clause constraints for DELETE / UPDATE
        for node in stmt.walk():
            if isinstance(node, exp.Delete) and "DELETE" in require_where:
                where = node.find(exp.Where)
                if not where or where.this is None:
                    return False, "DELETE without WHERE clause is strictly prohibited"
                if any(_is_tautology(w_node) for w_node in where.this.walk()):
                    return False, "Tautological WHERE condition detected on DELETE"

            if isinstance(node, exp.Update) and "UPDATE" in require_where:
                where = node.find(exp.Where)
                if not where or where.this is None:
                    return False, "UPDATE without WHERE clause is strictly prohibited"
                if any(_is_tautology(w_node) for w_node in where.this.walk()):
                    return False, "Tautological WHERE condition detected on UPDATE"

    return True, None


def check_path_safety(
    target_path: str,
    allowlist: Optional[list[str]] = None,
    denylist: Optional[list[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates file path confinement.
    Checks for:
    - Null bytes
    - Path traversal (..)
    - Symlink escape via realpath
    - Unmatched allowlist directories
    - Matched denylist paths
    """
    if not target_path or not isinstance(target_path, str):
        return False, "Empty or non-string path"

    # 1. Null byte detection
    if "\x00" in target_path or "%00" in target_path:
        return False, "Null byte injection detected in path"

    # 2. Denylist checking (patterns / raw sub-paths)
    if denylist:
        for denied in denylist:
            if denied in target_path:
                return False, f"Path matches denylist pattern: '{denied}'"

    # 3. Canonical realpath resolution
    try:
        canonical_target = os.path.realpath(os.path.abspath(target_path))
    except Exception as e:
        return False, f"Invalid path resolution: {str(e)}"

    # 4. Allowlist containment
    if allowlist:
        contained = False
        for allowed in allowlist:
            canonical_allowed = os.path.realpath(os.path.abspath(allowed))
            # Must either equal the allowed root or reside strictly within it
            if canonical_target == canonical_allowed or canonical_target.startswith(canonical_allowed + os.sep):
                contained = True
                break
        if not contained:
            return False, f"Path '{target_path}' is outside authorized directories: {allowlist}"

    return True, None


def check_domain_safety(
    url_or_domain: str,
    allowlist: Optional[list[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates network destination safety.
    Checks for:
    - Userinfo spoofing (e.g. allowed.com@evil.com)
    - Suffix confusion (e.g. allowed.com.evil.com)
    - IP literals vs allowed domains
    - Exact domain or exact subdomain boundary (.allowed.com)
    """
    if not url_or_domain or not isinstance(url_or_domain, str):
        return False, "Empty or non-string destination"

    if not allowlist:
        return True, None

    # Parse URL
    if not url_or_domain.startswith(("http://", "https://")):
        # Treat as raw domain or URL without scheme
        parsed = urllib.parse.urlsplit(f"http://{url_or_domain}")
    else:
        parsed = urllib.parse.urlsplit(url_or_domain)

    # urlsplit properly extracts hostname, ignoring userinfo (user:pass@)
    hostname = parsed.hostname
    if not hostname:
        return False, f"Could not determine valid hostname from: '{url_or_domain}'"

    hostname = hostname.lower().strip()

    # Normalize allowlist
    allowed_domains = [d.lower().strip() for d in allowlist]

    for allowed in allowed_domains:
        # 1. Exact match
        if hostname == allowed:
            return True, None

        # 2. Subdomain match on exact '.' boundary
        if hostname.endswith("." + allowed):
            return True, None

    return False, f"Domain '{hostname}' is not in allowlist: {allowlist}"
