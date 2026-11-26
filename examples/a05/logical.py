"""PostgreSQL の論理デコーディング: スロットを作り、変更を test_decoding と pgoutput で読みます。"""
import struct

TEXT_TYPES = {16: "bool", 20: "int", 21: "int", 23: "int"}


def create_slot(conn, slot, plugin):
    conn.execute("SELECT pg_create_logical_replication_slot(%s, %s)", (slot, plugin))


def drop_slot(conn, slot):
    conn.execute("SELECT pg_drop_replication_slot(%s)", (slot,))


def read_test_decoding(conn, slot, peek=False):
    """test_decoding の出力 (1 行 1 イベントの文字列) を読みます。get は読んだ分をスロットから進めます。"""
    fn = "pg_logical_slot_peek_changes" if peek else "pg_logical_slot_get_changes"
    return [row[2] for row in conn.execute(f"SELECT * FROM {fn}(%s, NULL, NULL)", (slot,)).fetchall()]


def read_pgoutput(conn, slot, publication, peek=False):
    """pgoutput のバイナリメッセージ (lsn, xid, データ) を読みます。"""
    fn = "pg_logical_slot_peek_binary_changes" if peek else "pg_logical_slot_get_binary_changes"
    return conn.execute(
        f"SELECT * FROM {fn}(%s, NULL, NULL, 'proto_version', '1', 'publication_names', %s)",
        (slot, publication)).fetchall()


class PgoutputDecoder:
    """pgoutput (プロトコル版 1) のメッセージを、変更の辞書に直します。

    扱うのは R (表の定義)・B/C (トランザクションの始まりと終わり)・I/U/D (行の変更) です。
    """

    def __init__(self):
        self.relations = {}  # relation id -> (表名, [(列名, 型 OID), ...])
        self.xid = None
        self.commit_lsn = None
        self.commit_ts_ms = None

    def _string(self, data, pos):
        end = data.index(b"\0", pos)
        return data[pos:end].decode(), end + 1

    def _tuple(self, relid, data, pos):
        (ncols,) = struct.unpack_from(">h", data, pos)
        pos += 2
        row = {}
        for name, type_oid in self.relations[relid][1][:ncols]:
            kind = data[pos:pos + 1]
            pos += 1
            if kind == b"n":
                row[name] = None
            elif kind == b"u":
                row[name] = "<unchanged-toast>"
            else:  # b"t": 4 バイトの長さ + 文字列
                (length,) = struct.unpack_from(">i", data, pos)
                text = data[pos + 4:pos + 4 + length].decode()
                pos += 4 + length
                row[name] = {"int": int, "bool": lambda t: t == "t"}.get(TEXT_TYPES.get(type_oid), str)(text)
        return row, pos

    def decode(self, data):
        """1 メッセージを読み、行の変更なら辞書を、それ以外は None を返します。"""
        kind = data[:1]
        if kind == b"B":
            self.commit_lsn, commit_us, self.xid = struct.unpack_from(">qqi", data, 1)
            self.commit_ts_ms = commit_us // 1000 + 946_684_800_000  # PostgreSQL の時刻は 2000-01-01 が起点
        elif kind == b"R":
            (relid,) = struct.unpack_from(">i", data, 1)
            namespace, pos = self._string(data, 5)
            name, pos = self._string(data, pos)
            pos += 1  # replica identity
            (ncols,) = struct.unpack_from(">h", data, pos)
            pos += 2
            cols = []
            for _ in range(ncols):
                pos += 1  # flags (1 ならキー列)
                col, pos = self._string(data, pos)
                (type_oid,) = struct.unpack_from(">i", data, pos)
                pos += 8  # 型 OID と typmod
                cols.append((col, type_oid))
            self.relations[relid] = (f"{namespace}.{name}", cols)
        elif kind in (b"I", b"U", b"D"):
            (relid,) = struct.unpack_from(">i", data, 1)
            pos, old, new, old_kind = 5, None, None, None
            while pos < len(data):
                tag = data[pos:pos + 1]
                pos += 1
                row, pos = self._tuple(relid, data, pos)
                if tag in (b"K", b"O"):
                    old, old_kind = row, tag.decode()  # K: キー列だけ / O: 行全体
                else:
                    new = row
            op = {b"I": "insert", b"U": "update", b"D": "delete"}[kind]
            return {"op": op, "table": self.relations[relid][0], "xid": self.xid,
                    "lsn": self.commit_lsn, "ts_ms": self.commit_ts_ms,
                    "old": old, "old_kind": old_kind, "new": new}
        return None

    def changes(self, messages):
        out = (self.decode(bytes(m[2])) for m in messages)
        return [c for c in out if c]


def slot_status(conn, slot):
    """スロットが止めている WAL の量 (バイト) と状態を返します。"""
    row = conn.execute(
        "SELECT active, wal_status, safe_wal_size, "
        "pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint "
        "FROM pg_replication_slots WHERE slot_name = %s", (slot,)).fetchone()
    return {"active": row[0], "wal_status": row[1], "safe_wal_size": row[2], "retained_bytes": row[3]}
