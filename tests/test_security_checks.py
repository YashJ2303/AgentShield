import os
import tempfile
import pytest
from server.app.services.security_checks import (
    check_sql_safety,
    check_path_safety,
    check_domain_safety,
)


# =====================================================================
# 1. SQL Bypass Tests
# =====================================================================

def test_sql_multi_statement_injection():
    # Multi-statement injection hiding a DROP or unrestricted DELETE behind a benign SELECT
    malicious = "SELECT 1; DROP TABLE users;"
    is_safe, err = check_sql_safety(malicious)
    assert not is_safe
    assert "Destructive SQL operation" in err or "DROP" in err or "Blocked SQL" in err

    malicious_delete = "SELECT * FROM orders; DELETE FROM accounts;"
    is_safe, err = check_sql_safety(malicious_delete, allowed_operations=["SELECT", "DELETE"])
    assert not is_safe
    assert "DELETE without WHERE" in err


def test_sql_multi_statement_where_clause_scoping():
    """Verify that multi-statement queries do not bypass WHERE clause checks due to AST scoping."""
    # Query with DELETE without WHERE followed by a harmless SELECT
    query_delete_first = "DELETE FROM accounts; SELECT * FROM orders;"
    is_safe, err = check_sql_safety(
        query_delete_first,
        allowed_operations=["SELECT", "DELETE"],
        require_where_clause_on=["DELETE", "UPDATE"],
    )
    assert not is_safe
    assert "DELETE without WHERE" in err

    # Query with UPDATE without WHERE followed by a harmless SELECT
    query_update_first = "UPDATE accounts SET balance = 0; SELECT 1;"
    is_safe, err = check_sql_safety(
        query_update_first,
        allowed_operations=["SELECT", "UPDATE"],
        require_where_clause_on=["DELETE", "UPDATE"],
    )
    assert not is_safe
    assert "UPDATE without WHERE" in err



def test_sql_comment_hidden_keywords():
    # Comment-hidden SQL operation
    malicious = "SELECT * FROM users; /* inline comment */ DROP TABLE logs;"
    is_safe, err = check_sql_safety(malicious)
    assert not is_safe
    assert "Destructive SQL operation" in err or "DROP" in err or "Blocked SQL" in err


def test_sql_cte_wrapped_delete():
    # CTE wrapping a DELETE without a valid WHERE clause
    cte_query = "WITH target_rows AS (SELECT id FROM users) DELETE FROM users;"
    is_safe, err = check_sql_safety(cte_query, allowed_operations=["SELECT", "DELETE"])
    assert not is_safe
    assert "DELETE without WHERE" in err


def test_sql_tautological_where_clauses():
    # Tautological conditions designed to wipe entire table
    tautologies = [
        "DELETE FROM users WHERE 1=1;",
        "UPDATE accounts SET balance=0 WHERE 'a'='a';",
        "DELETE FROM audit_logs WHERE true;",
        "DELETE FROM users WHERE id=5 OR 1=1;",
        "DELETE FROM users WHERE 1<2;",
        "DELETE FROM users WHERE id IS NOT NULL;",
    ]
    for query in tautologies:
        is_safe, err = check_sql_safety(
            query,
            allowed_operations=["SELECT", "UPDATE", "DELETE"],
        )
        assert not is_safe, f"Failed to block tautological WHERE in: {query}"
        assert "Tautological WHERE condition" in err


def test_sql_select_only_default():
    # By default, SQL checks allow SELECT only; INSERT/UPDATE/DELETE are rejected unless rule permits more
    select_query = "SELECT id, name FROM users WHERE id = 42;"
    is_safe, err = check_sql_safety(select_query)
    assert is_safe, f"Expected SELECT to pass by default, got: {err}"

    write_queries = [
        "UPDATE users SET name='Alice' WHERE id = 101;",
        "DELETE FROM sessions WHERE expired_at < '2026-01-01';",
        "INSERT INTO users (id, name) VALUES (1, 'Eve');",
    ]
    for q in write_queries:
        is_safe, err = check_sql_safety(q)
        assert not is_safe, f"Expected write query to be blocked by SELECT-only default: {q}"
        assert "not permitted by policy" in err or "allowed operations" in err


def test_sql_blocked_administrative_and_ddl():
    # ATTACH, PRAGMA, REPLACE, VACUUM INTO, CREATE, GRANT, DROP, TRUNCATE, ALTER are blocked
    blocked_queries = [
        "ATTACH DATABASE 'evil.db' AS evil;",
        "PRAGMA journal_mode=WAL;",
        "REPLACE INTO users (id, name) VALUES (1, 'admin');",
        "VACUUM INTO '/tmp/pwn.db';",
        "VACUUM;",
        "CREATE TABLE evil (id INT);",
        "GRANT ALL PRIVILEGES ON users TO attacker;",
        "REVOKE SELECT ON users FROM analyst;",
        "DROP TABLE users;",
        "TRUNCATE TABLE users;",
        "ALTER TABLE users ADD COLUMN backdoor TEXT;",
    ]
    for q in blocked_queries:
        is_safe, err = check_sql_safety(q, allowed_operations=["*"])
        assert not is_safe, f"Expected blocked operation to be denied: {q}"
        assert "Blocked SQL" in err or "Destructive" in err or "syntax error" in err


def test_sql_unparseable_fails_closed():
    # Invalid / unparseable SQL must be denied
    garbage_queries = [
        "SELECT FROM WHERE ;;; DROP ???",
        "INVALID SYNTAX @#$!%",
        "",
    ]
    for q in garbage_queries:
        is_safe, err = check_sql_safety(q)
        assert not is_safe, f"Expected unparseable SQL to fail closed: '{q}'"


def test_sql_benign_queries_allowed():
    benign_selects = [
        "SELECT id, name FROM users WHERE id = 42;",
        "SELECT count(*) FROM orders JOIN users ON orders.user_id = users.id;",
    ]
    for q in benign_selects:
        is_safe, err = check_sql_safety(q)
        assert is_safe, f"Expected benign SELECT query to pass: '{q}', got error: {err}"

    # Permitted write operations with valid non-tautological WHERE clauses
    benign_writes = [
        "UPDATE users SET name='Alice' WHERE id = 101;",
        "DELETE FROM sessions WHERE expired_at < '2026-01-01';",
    ]
    for q in benign_writes:
        is_safe, err = check_sql_safety(q, allowed_operations=["SELECT", "UPDATE", "DELETE"])
        assert is_safe, f"Expected permitted write query to pass: '{q}', got error: {err}"


def test_sql_replace_function_in_select_allowed_while_replace_into_blocked():
    """
    Ensure REPLACE is blocked ONLY as a statement (REPLACE INTO) via the AST,
    and NOT when used as a standard SQL scalar string function within SELECT.
    """
    # 1. Scalar REPLACE() function in SELECT queries should pass cleanly
    scalar_replace_queries = [
        "SELECT REPLACE(name, 'a', 'b') FROM users;",
        "SELECT id, REPLACE(email, '@old.com', '@new.com') AS clean_email FROM customers WHERE id = 5;",
        "SELECT REPLACE(REPLACE(title, 'Mr.', ''), 'Ms.', '') FROM employees;",
    ]
    for q in scalar_replace_queries:
        is_safe, err = check_sql_safety(q)
        assert is_safe, f"Expected scalar REPLACE() function in SELECT to be allowed: '{q}', error: {err}"

    # 2. REPLACE INTO statement must be strictly blocked
    replace_into_queries = [
        "REPLACE INTO users (id, name) VALUES (1, 'admin');",
        "REPLACE INTO config (key, val) VALUES ('mode', 'debug');",
    ]
    for q in replace_into_queries:
        is_safe, err = check_sql_safety(q, allowed_operations=["*"])
        assert not is_safe, f"Expected statement-level REPLACE INTO to be blocked: '{q}'"
        assert "Blocked SQL" in err or "REPLACE" in err


# =====================================================================
# 2. Path Confinement Bypass Tests
# =====================================================================

def test_path_traversal_dot_dot():
    allowlist = ["./sandbox"]
    traversals = [
        "./sandbox/../../etc/passwd",
        "./sandbox/../secret.env",
        "sandbox/..\\..\\windows\\system32",
    ]
    for p in traversals:
        is_safe, err = check_path_safety(p, allowlist=allowlist)
        assert not is_safe, f"Failed to block path traversal: {p}"
        assert "outside authorized directories" in err or "denylist" in err


def test_path_null_bytes():
    allowlist = ["./sandbox"]
    null_byte_paths = [
        "./sandbox/file.txt\x00.exe",
        "./sandbox/data%00.txt",
    ]
    for p in null_byte_paths:
        is_safe, err = check_path_safety(p, allowlist=allowlist)
        assert not is_safe, f"Failed to block null byte in path: {p}"
        assert "Null byte" in err


def test_path_absolute_paths_outside_sandbox():
    allowlist = ["./sandbox"]
    absolutes = [
        "/etc/shadow",
        "C:\\Windows\\System32\\cmd.exe",
        "D:\\sensitive_data\\secret.key",
    ]
    for p in absolutes:
        is_safe, err = check_path_safety(p, allowlist=allowlist)
        assert not is_safe, f"Failed to block unauthorized absolute path: {p}"


def test_path_symlink_escape():
    # Create temporary sandbox and external target directory
    with tempfile.TemporaryDirectory() as base_temp:
        sandbox_dir = os.path.join(base_temp, "sandbox")
        outside_dir = os.path.join(base_temp, "outside")
        os.makedirs(sandbox_dir, exist_ok=True)
        os.makedirs(outside_dir, exist_ok=True)

        outside_secret = os.path.join(outside_dir, "secret.txt")
        with open(outside_secret, "w") as f:
            f.write("sensitive data")

        # Create symlink inside sandbox pointing outside
        symlink_path = os.path.join(sandbox_dir, "link_to_secret.txt")
        try:
            os.symlink(outside_secret, symlink_path)
            # check_path_safety on symlink must resolve realpath outside sandbox and deny
            is_safe, err = check_path_safety(symlink_path, allowlist=[sandbox_dir])
            assert not is_safe
            assert "outside authorized directories" in err
        except OSError:
            # On Windows without SeCreateSymbolicLinkPrivilege, symlink creation might skip
            pass


def test_path_benign_sandbox_access():
    with tempfile.TemporaryDirectory() as sandbox:
        safe_file = os.path.join(sandbox, "data.csv")
        with open(safe_file, "w") as f:
            f.write("a,b,c")

        is_safe, err = check_path_safety(safe_file, allowlist=[sandbox])
        assert is_safe, f"Expected safe sandbox file to pass, got: {err}"


# =====================================================================
# 3. Domain Spoofing & Boundary Tests
# =====================================================================

def test_domain_userinfo_spoofing():
    # Attacker uses allowed.com as userinfo: allowed.com@evil.com
    allowlist = ["allowed.com", "docs.python.org"]
    spoofed = [
        "http://allowed.com@evil.com/payload",
        "https://docs.python.org:mypassword@malicious-site.net/api",
    ]
    for url in spoofed:
        is_safe, err = check_domain_safety(url, allowlist=allowlist)
        assert not is_safe, f"Failed to block userinfo spoofing in: {url}"
        assert "not in allowlist" in err


def test_domain_suffix_confusion():
    # Attacker owns allowed.com.evil.com
    allowlist = ["allowed.com"]
    confused = [
        "https://allowed.com.evil.com",
        "http://allowed.com-phishing.org",
    ]
    for url in confused:
        is_safe, err = check_domain_safety(url, allowlist=allowlist)
        assert not is_safe, f"Failed to block suffix confusion in: {url}"
        assert "not in allowlist" in err


def test_domain_subdomain_boundary():
    # If allowed domain is 'allowed.com':
    # - sub.allowed.com is valid (has exact '.' boundary)
    # - fakeallowed.com is invalid (no '.' boundary)
    allowlist = ["allowed.com"]

    # Valid subdomains
    assert check_domain_safety("https://api.allowed.com/v1", allowlist=allowlist)[0] is True
    assert check_domain_safety("https://deep.sub.allowed.com", allowlist=allowlist)[0] is True
    assert check_domain_safety("https://allowed.com", allowlist=allowlist)[0] is True

    # Invalid boundary
    is_safe, err = check_domain_safety("https://fakeallowed.com", allowlist=allowlist)
    assert is_safe is False
    assert "not in allowlist" in err


def test_domain_ip_literals():
    allowlist = ["docs.python.org", "api.company.internal"]
    ip_urls = [
        "http://192.168.1.1/admin",
        "http://127.0.0.1:8000/internal",
        "http://10.0.0.5",
    ]
    for url in ip_urls:
        is_safe, err = check_domain_safety(url, allowlist=allowlist)
        assert not is_safe, f"Failed to block IP literal not in allowlist: {url}"
