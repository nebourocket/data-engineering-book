"""ビルドや apply をしなくてもできる、設定ファイルの簡単な検査です。

Dockerfile・compose・Terraform・IAM ポリシーを「読んで形を確かめる」だけで、動かしはしません。
本物の検査 (docker build / terraform validate) の代わりではなく、レビューで見落としやすい
決まりごとを CI で毎回確かめるための安全網です。各関数は問題の説明文のリストを返します (空なら問題なし)。
"""
import json
import re

SECRET_NAME = re.compile(r"(KEY|SECRET|PASSWORD|TOKEN)", re.I)


def dockerfile_problems(text, requirements=""):
    # 行末の \ でつながった行を 1 行にし、コメントと空行を捨てる
    lines = [ln.strip() for ln in re.sub(r"\\\n", " ", text).splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    problems = []

    froms = [ln.split()[1] for ln in lines if ln.upper().startswith("FROM ")]
    for image in froms:
        if ":" not in image and "@sha256:" not in image:
            problems.append(f"FROM {image}: タグが無い (latest になる)")
        elif image.endswith(":latest"):
            problems.append(f"FROM {image}: latest は固定されない")

    users = [ln.split()[1] for ln in lines if ln.upper().startswith("USER ")]
    if not users or users[-1] in ("root", "0"):
        problems.append("最後の USER が root (または USER が無い)")

    copies = [ln for ln in lines if ln.upper().startswith("COPY ")]
    first_copy = copies[0].split() if copies else []
    if not any("requirements" in tok for tok in first_copy):
        problems.append("最初の COPY が requirements でない (コードの変更で依存の層が毎回作り直しになる)")

    for ln in lines:
        if "pip install" in ln and "--no-cache-dir" not in ln:
            problems.append("pip install に --no-cache-dir が無い (キャッシュがイメージに残る)")
        if re.match(r"(ENV|ARG)\s", ln, re.I) and SECRET_NAME.search(ln.split("=")[0]):
            problems.append(f"秘密らしい名前の ENV/ARG: {ln}")
        if re.match(r"COPY\s.*\.env\b", ln, re.I):
            problems.append(f"{ln}: .env をイメージに入れている")

    cmds = [ln for ln in lines if ln.upper().startswith(("CMD ", "ENTRYPOINT "))]
    if not cmds or not all(ln.split(None, 1)[1].lstrip().startswith("[") for ln in cmds):
        problems.append("CMD/ENTRYPOINT が exec 形式 (JSON 配列) でない")

    for req in requirements.splitlines():
        req = req.strip()
        if req and not req.startswith("#") and "==" not in req:
            problems.append(f"requirements: {req} がバージョン固定されていない")
    return problems


def compose_problems(spec):
    """spec は yaml.safe_load した compose.yaml。"""
    problems = []
    services = spec.get("services", {})
    for name, svc in services.items():
        image = svc.get("image")
        if image and (":" not in image or image.endswith(":latest")):
            problems.append(f"{name}: image {image} のタグが固定されていない")
        for dep, cond in (svc.get("depends_on") or {}).items():
            if not isinstance(cond, dict) or cond.get("condition") != "service_healthy":
                problems.append(f"{name}: {dep} の起動完了を待っていない (service_healthy が無い)")
            elif "healthcheck" not in services.get(dep, {}):
                problems.append(f"{name}: {dep} に healthcheck が無い")
        for key, value in (svc.get("environment") or {}).items():
            if SECRET_NAME.search(key) and not str(value).startswith("${"):
                problems.append(f"{name}: {key} の値が compose に直書きされている")
    return problems


def terraform_problems(text):
    problems = []
    # 文字列とコメントを消してから、括弧の釣り合いと resource の種類を見る
    bare = re.sub(r'"[^"\n]*"', '""', re.sub(r"(?m)^\s*(#|//).*$", "", text))
    if bare.count("{") != bare.count("}"):
        problems.append("波括弧 { } の数が合わない")
    kinds = set(re.findall(r'resource\s+"(\w+)"', text))
    for need in ("aws_s3_bucket", "aws_s3_bucket_public_access_block",
                 "aws_s3_bucket_server_side_encryption_configuration"):
        if need not in kinds:
            problems.append(f"{need} が無い")
    if re.search(r"AKIA[0-9A-Z]{16}|secret_key|access_key", text):
        problems.append("アクセスキーらしい文字列がある")
    if not re.search(r"bucket\s*=\s*var\.bucket_name", text):
        problems.append("バケット名が変数になっていない")
    for flag in ("block_public_acls", "block_public_policy",
                 "ignore_public_acls", "restrict_public_buckets"):
        if not re.search(rf"{flag}\s*=\s*true", text):
            problems.append(f"{flag} が true でない")
    return problems


def policy_problems(text):
    problems = []
    for st in json.loads(text)["Statement"]:
        actions = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
        resources = st["Resource"] if isinstance(st["Resource"], list) else [st["Resource"]]
        if any(a in ("*", "s3:*") for a in actions):
            problems.append(f"{st.get('Sid')}: Action が広すぎる")
        if any(r == "*" for r in resources):
            problems.append(f"{st.get('Sid')}: Resource が * ")
        if "s3:ListBucket" in actions and any(r.endswith("/*") for r in resources):
            problems.append(f"{st.get('Sid')}: ListBucket の対象はバケット (末尾 /* にしない)")
        if "s3:GetObject" in actions and any(not r.endswith("/*") and "/" not in r.split(":::")[1]
                                             for r in resources):
            problems.append(f"{st.get('Sid')}: GetObject の対象はオブジェクト (…/* にする)")
    return problems
