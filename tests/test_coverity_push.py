"""Tests for the server-free push pipeline in coverity_push.py."""
import pytest

import coverity_push as cp


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeClient:
    """Stands in for CoveritySOAPClient.update_triage."""

    def __init__(self, fail_cids=(), error=None, raise_exc=None,
                 understate_success=False):
        self.calls = []
        self.fail_cids = set(fail_cids)
        self.error = error
        self.raise_exc = raise_exc
        self.understate_success = understate_success

    def update_triage(self, cid_list, triage_store_name, classification, comment, action=None):
        self.calls.append((list(cid_list), triage_store_name, classification, comment, action))
        if self.raise_exc:
            raise RuntimeError(self.raise_exc)
        failed = [c for c in cid_list if c in self.fail_cids]
        if self.understate_success:
            return 0, [], self.error
        return len(cid_list) - len(failed), failed, self.error


def defect(cid, cls="Bug", accepted=False, **kw):
    d = {"cid": cid, "classification": cls, "comment": f"c{cid}",
         "checker": "OVERRUN", "file": f"/src/f{cid}.c", "line": 10,
         "accepted": accepted}
    d.update(kw)
    return d


# --------------------------------------------------------------------------- #
# select_defects
# --------------------------------------------------------------------------- #
def test_select_all_keeps_everything_with_a_cid():
    results = [defect(1), defect(2, accepted=True), {"cid": None}]
    assert [d["cid"] for d in cp.select_defects(results, cp.MODE_ALL)] == [1, 2]


def test_select_accepted_only_takes_reviewed_defects():
    results = [defect(1), defect(2, accepted=True), defect(3, overridden=True)]
    got = cp.select_defects(results, cp.MODE_ACCEPTED)
    assert [d["cid"] for d in got] == [2, 3]


def test_select_decided_excludes_needs_review():
    results = [defect(1, cls="Needs review"), defect(2, cls="False positive")]
    got = cp.select_defects(results, cp.MODE_DECIDED)
    assert [d["cid"] for d in got] == [2]


def test_select_drops_non_numeric_cids():
    assert cp.select_defects([{"cid": "abc", "classification": "Bug"}], cp.MODE_ALL) == []


def test_select_rejects_unknown_mode():
    with pytest.raises(ValueError):
        cp.select_defects([defect(1)], "sideways")


# --------------------------------------------------------------------------- #
# build_push_rows
# --------------------------------------------------------------------------- #
def test_build_rows_maps_classification_to_server_value():
    rows = cp.build_push_rows([defect(1, cls="False positive")])
    assert rows[0].server_classification == "False Positive"


def test_accepted_pushes_underlying_classification_not_the_word_accepted():
    rows = cp.build_push_rows(
        [defect(1, cls="Accepted", base_classification="False positive")])
    assert rows[0].classification == "False positive"


def test_comment_gets_provenance_stamp_once():
    rows = cp.build_push_rows([defect(1)], reviewer="rakesh")
    assert "Coverity Tool" in rows[0].comment and "rakesh" in rows[0].comment
    again = cp.build_push_rows(
        [defect(1, comment=rows[0].comment)], reviewer="rakesh")
    assert again[0].comment.count("Coverity Tool") == 1


def test_comment_stamp_can_be_disabled_and_is_truncated():
    rows = cp.build_push_rows([defect(1, comment="x" * 50)],
                              stamp_comment=False, max_comment=20)
    assert len(rows[0].comment) == 20 and rows[0].comment.endswith("…")


def test_duplicate_cids_collapse_to_last():
    rows = cp.build_push_rows([defect(1, cls="Bug"), defect(1, cls="Intentional")])
    assert len(rows) == 1 and rows[0].classification == "Intentional"


def test_action_defaults_from_classification_when_missing():
    assert cp.build_push_rows([defect(1, cls="Bug")])[0].server_action == "Fix Required"
    assert cp.build_push_rows([defect(2, cls="False positive")])[0].server_action == "Ignore"
    assert cp.build_push_rows([defect(3, cls="Needs review")])[0].server_action == "Undecided"


def test_action_is_read_and_normalized_from_output_rows():
    rows = cp.build_push_rows([defect(1, action="modelling required")])
    assert rows[0].server_action == "Modeling Required"


# --------------------------------------------------------------------------- #
# validate_rows
# --------------------------------------------------------------------------- #
def test_exact_cid_match():
    rows = cp.build_push_rows([defect(7)])
    rep = cp.validate_rows(rows, [{"cid": 7, "checker": "OVERRUN", "file": "/x/f7.c"}])
    assert rep.matched and rows[0].server_cid == 7 and rows[0].match == "cid"


def test_stale_cid_remaps_by_file_and_checker():
    rows = cp.build_push_rows([defect(7)])
    rep = cp.validate_rows(
        rows, [{"cid": 99, "checker": "OVERRUN", "file": "/other/path/f7.c"}])
    assert rep.remapped and rows[0].server_cid == 99 and rows[0].match == "signature"


def test_ambiguous_signature_is_not_guessed():
    rows = cp.build_push_rows([defect(7)])
    server = [{"cid": 98, "checker": "OVERRUN", "file": "/a/f7.c"},
              {"cid": 99, "checker": "OVERRUN", "file": "/b/f7.c"}]
    rep = cp.validate_rows(rows, server)
    assert rep.unmatched and rows[0].server_cid is None


def test_unknown_defect_is_unmatched():
    rows = cp.build_push_rows([defect(7)])
    rep = cp.validate_rows(rows, [{"cid": 1, "checker": "RESOURCE_LEAK", "file": "/z.c"}])
    assert rep.unmatched and "not found" in rep.summary()


# --------------------------------------------------------------------------- #
# group_rows / batching
# --------------------------------------------------------------------------- #
def test_rows_sharing_classification_and_comment_batch_together():
    rows = cp.build_push_rows([defect(1, comment="same"), defect(2, comment="same")],
                              stamp_comment=False)
    batches = cp.group_rows(rows)
    assert len(batches) == 1 and len(batches[0][3]) == 2


def test_differing_comments_are_separate_calls():
    rows = cp.build_push_rows([defect(1), defect(2)], stamp_comment=False)
    assert len(cp.group_rows(rows)) == 2


def test_batches_respect_the_hundred_cid_server_limit():
    rows = cp.build_push_rows(
        [defect(i, comment="same") for i in range(1, 251)], stamp_comment=False)
    batches = cp.group_rows(rows)
    assert [len(b[3]) for b in batches] == [100, 100, 50]


# --------------------------------------------------------------------------- #
# push_rows
# --------------------------------------------------------------------------- #
def _validated(defects, server=None):
    rows = cp.build_push_rows(defects, stamp_comment=False)
    cp.validate_rows(rows, server or [{"cid": d["cid"], "checker": d["checker"],
                                       "file": d["file"]} for d in defects])
    return rows


def test_successful_push_marks_every_row():
    rows = _validated([defect(1), defect(2)])
    client = FakeClient()
    rep = cp.push_rows(client, rows, "MyStore")
    assert rep.ok and len(rep.succeeded) == 2
    assert all(r.status == "✓" for r in rows)
    assert client.calls[0][1] == "MyStore"
    assert client.calls[0][4] == "Fix Required"


def test_partial_failure_is_reported_per_cid():
    rows = _validated([defect(1, comment="s"), defect(2, comment="s")])
    rep = cp.push_rows(FakeClient(fail_cids=[2], error="SOAP Fault: nope"), rows, "S")
    assert [r.cid for r in rep.succeeded] == [1]
    assert [r.cid for r in rep.failed] == [2]
    assert not rep.ok


def test_unvalidated_rows_are_skipped_not_pushed():
    rows = cp.build_push_rows([defect(1)], stamp_comment=False)  # never validated
    client = FakeClient()
    rep = cp.push_rows(client, rows, "S")
    assert rep.skipped and not client.calls and rows[0].status == "–"


def test_unvalidated_rows_can_be_forced():
    rows = cp.build_push_rows([defect(1)], stamp_comment=False)
    rep = cp.push_rows(FakeClient(), rows, "S", require_validated=False)
    assert len(rep.succeeded) == 1


def test_dry_run_never_calls_the_server():
    rows = _validated([defect(1)])
    client = FakeClient()
    rep = cp.push_rows(client, rows, "S", dry_run=True)
    assert client.calls == [] and rep.dry_run and len(rep.succeeded) == 1
    assert "Dry run" in rep.summary()


def test_missing_triage_store_fails_closed():
    rows = _validated([defect(1)])
    client = FakeClient()
    rep = cp.push_rows(client, rows, "")
    assert not client.calls and rep.failed and not rep.ok


def test_transport_exception_fails_the_batch_instead_of_propagating():
    rows = _validated([defect(1)])
    rep = cp.push_rows(FakeClient(raise_exc="connection reset"), rows, "S")
    assert rep.failed and "connection reset" in rep.errors[0]


def test_unexplained_shortfall_counts_as_failure():
    """Server says 0 succeeded but names no failed CIDs — never claim success."""
    rows = _validated([defect(1, comment="s"), defect(2, comment="s")])
    rep = cp.push_rows(FakeClient(understate_success=True), rows, "S")
    assert len(rep.failed) == 2 and not rep.succeeded


def test_remapped_row_pushes_the_server_cid():
    rows = cp.build_push_rows([defect(7)], stamp_comment=False)
    cp.validate_rows(rows, [{"cid": 99, "checker": "OVERRUN", "file": "/q/f7.c"}])
    client = FakeClient()
    cp.push_rows(client, rows, "S")
    assert client.calls[0][0] == [99]


def test_progress_callback_reports_each_row():
    rows = _validated([defect(1), defect(2)])
    seen = []
    cp.push_rows(FakeClient(), rows, "S",
                 progress_cb=lambda done, total, row: seen.append((done, total)))
    assert seen == [(1, 2), (2, 2)]


# --------------------------------------------------------------------------- #
# apply_status_to_results
# --------------------------------------------------------------------------- #
def test_statuses_flow_back_onto_the_results_table():
    results = [defect(1), defect(2)]
    rows = _validated(results)
    cp.push_rows(FakeClient(fail_cids=[2]), rows, "S")
    assert cp.apply_status_to_results(results, rows) == 2
    assert results[0]["push_status"] == "✓"
    assert results[1]["push_status"] == "✗"


# --------------------------------------------------------------------------- #
# end-to-end: analysed results -> push -> table colouring
# --------------------------------------------------------------------------- #
def test_full_flow_from_results_table_to_server():
    """Mirrors what DirectPushDialog does, minus Tk."""
    results = [
        defect(101, cls="Bug", accepted=True),
        defect(102, cls="False positive", accepted=True),
        defect(103, cls="Needs review"),          # not reviewed -> excluded
        defect(104, cls="Intentional", accepted=True),  # stale CID -> remapped
    ]
    server = [
        {"cid": 101, "checker": "OVERRUN", "file": "/build/f101.c"},
        {"cid": 102, "checker": "OVERRUN", "file": "/build/f102.c"},
        {"cid": 900, "checker": "OVERRUN", "file": "/build/f104.c"},
    ]

    selected = cp.select_defects(results, cp.MODE_ACCEPTED)
    assert [d["cid"] for d in selected] == [101, 102, 104]

    rows = cp.build_push_rows(selected, reviewer="qa")
    report = cp.validate_rows(rows, server)
    assert len(report.matched) == 2 and len(report.remapped) == 1

    client = FakeClient()
    push = cp.push_rows(client, rows, "MyProject")
    assert push.ok and len(push.succeeded) == 3

    # the remapped defect must be written under the server's CID, not the stale one
    pushed_cids = sorted(c for call in client.calls for c in call[0])
    assert pushed_cids == [101, 102, 900]

    cp.apply_status_to_results(results, rows)
    assert results[0]["push_status"] == "✓"
    assert "push_status" not in results[2]      # excluded defect untouched
    assert results[3]["pushed_cid"] == 900


def test_dry_run_then_real_push_writes_once():
    results = [defect(1, accepted=True)]
    rows = _validated(cp.select_defects(results, cp.MODE_ACCEPTED))
    client = FakeClient()
    cp.push_rows(client, rows, "S", dry_run=True)
    assert client.calls == []
    cp.push_rows(client, rows, "S")
    assert len(client.calls) == 1
