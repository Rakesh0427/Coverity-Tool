# Disposition Comment & Proposed Fix Examples

This document shows how the tool now phrases disposition comments and proposed fixes for the main Coverity checkers, across different scenarios. Each example shows:

- **Scenario** — the code pattern the tool is reviewing.
- **Verdict** — Bug / False positive / Intentional / Needs review.
- **Comment** — the senior-reviewer disposition text that is printed.
- **Proposed fix** — what the Proposed Fix panel shows.

---

## 1. BUFFER_SIZE

### 1.1 Bug — `strncpy(dest, src, sizeof(dest))` leaves the string unterminated

```c
void copy(const char *src)
{
    char name[32];
    strncpy(name, src, sizeof(name));
    log(name);
}
```

**Verdict:** `Bug`

**Comment:**
> strncpy() at line 4 copies exactly sizeof(name) bytes into `name`, filling it completely and leaving no room for the null terminator; `name` is never null-terminated after the copy. Reference: CWE-120 (Buffer Copy without Checking Size of Input), CERT STR31-C, OWASP Not directly applicable (native-code / non-web defect). Any later string operation reads past the end of the buffer (out-of-bounds read).

**Proposed fix:**
```c
strncpy(name, src, sizeof(name)-1); name[sizeof(name)-1]='\0';
```

---

### 1.2 False positive — destination is pre-zeroed with `memset`

```c
void copy(char *src)
{
    char name[16];
    memset(name, 0, sizeof(name));
    strncpy(name, src, sizeof(name));
    send(name);
}
```

**Verdict:** `False positive`

**Comment:**
> `strncpy()` at line 4 copies into `name` bounded by `sizeof(name)` from `src`, and `name` is pre-zeroed with memset at line 3, which keeps the buffer null-terminated. False positive.

**Proposed fix:**

```text
No fix required.
```

---

### 1.3 False positive — fixed-width struct field copied with its exact size

```c
struct Rec { char center_name[8]; };
void set_center(struct Rec *r, const char *src)
{
    strncpy(r->center_name, src, 8);
}
```

**Verdict:** `False positive`

**Comment:**
> The BUFFER_SIZE at line 3 is not a real defect: strncpy(r->c, s, 8) copies exactly 8 bytes into r->c, which is declared with size 8 — the copy fills the field exactly and is a fixed-width transfer, not an open-ended C-string write. False positive.

**Proposed fix:**

```text
No fix required.
```

---

### 1.4 False positive — explicit length check before the copy

```c
void fn(char *src)
{
    char name[16];
    if (strlen(src) >= sizeof(name)) {
        return;
    }
    strncpy(name, src, sizeof(name) - 1);
    name[sizeof(name) - 1] = '\0';
    send(name);
}
```

**Verdict:** `False positive`

**Comment:**
> The BUFFER_SIZE at line 7 is not a real defect: copy is performed only after the source length is validated at line 5, and the destination is explicitly null-terminated at line 8. False positive.

**Proposed fix:**

```text
No fix required.
```

---

### 1.5 False positive — destination is larger than the payload copied

```c
void fn(void)
{
    char uc_afn_msg[121];
    strncpy(uc_afn_msg, "ATC", 3);
    uc_afn_msg[3] = '\0';
    send(uc_afn_msg);
}
```

**Verdict:** `False positive`

**Comment:**
> `strncpy()` at line 3 copies into `uc_afn_msg` bounded by `3` from the string literal, and the null terminator is explicitly written at line 4 before the buffer is used further. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 2. STRING_NULL

### 2.1 Bug — source length used as copy count leaves the destination unterminated

```c
void build(const char *src)
{
    char name[32];
    strncpy(name, src, strlen(src));
    log(name);
}
```

**Verdict:** `Bug`

**Comment:**
> strncpy() at line 3 uses `strlen` (`strlen(src)`) as the copy count. strncpy does not append a null terminator when n equals the source length, so `name` is left unterminated and any later string use reads past the end of the buffer. Reference: CWE-170 (Improper Null Termination), CERT STR32-C, OWASP Not directly applicable (native-code / non-web defect).

**Proposed fix:**
```c
name[sizeof(name) - 1] = '\0';
```

---

### 2.2 False positive — buffer is pre-zeroed before the copy

```c
void build(const char *src)
{
    char name[32];
    memset(name, 0, sizeof(name));
    strncpy(name, src, sizeof(name));
}
```

**Verdict:** `False positive`

**Comment:**
> `strncpy()` at line 4 copies into `name` bounded by `sizeof(name)` from `src`, and `name` is pre-zeroed with memset at line 3, which keeps the buffer null-terminated. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 3. OVERRUN

### 3.1 Bug — inclusive `<=` guard is an off-by-one

```c
#define MAX_NUM_ADS_CONNECTIONS 16
static rpt_rec_t gs_ec_rpt_tbl[MAX_NUM_ADS_CONNECTIONS];

void fn(unsigned int ui_conn_index)
{
    if (ui_conn_index <= MAX_NUM_ADS_CONNECTIONS) {
        gs_ec_rpt_tbl[ui_conn_index].ui_supp_ec_bitmask = 1;
    }
}
```

**Verdict:** `Bug`

**Comment:**
> `gs_ec_rpt_tbl[ui_conn_index]` is written at line 6. Condition at line 6 (`ui_conn_index <= MAX_NUM_ADS_CONNECTIONS`) allows `ui_conn_index` to reach `16`. `gs_ec_rpt_tbl` is declared with 16 elements (valid indices 0 to 15). The guard permits index 16, which is beyond the valid range — confirmed out-of-bounds written. The `<=` allows index == 16, which is one past the last valid index (15) — an off-by-one out-of-bounds access; the check must be `<`.
>
> Reference: CWE-125 (Out-of-bounds Read) | CERT ARR30-C | https://cwe.mitre.org/data/definitions/125.html

**Proposed fix:**
> Add the guard `if (ui_conn_index < 0 || ui_conn_index >= (int)(sizeof(gs_ec_rpt_tbl) / sizeof(gs_ec_rpt_tbl[0])))` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

### 3.2 Bug — access inside the `else` of a failed bounds check

```c
#define MAX_NUM_ADS_CONNECTIONS 16
static unsigned char gs_byDsiStartInd[MAX_NUM_ADS_CONNECTIONS];

void fn(unsigned int ui_conn_index)
{
    if (ui_conn_index < MAX_NUM_ADS_CONNECTIONS) {
        ok();
    } else {
        memset(&gs_byDsiStartInd[ui_conn_index], 0, 1);
    }
}
```

**Verdict:** `Bug`

**Comment:**
> `gs_byDsiStartInd[ui_conn_index]` is written at line 8. The access is inside the `else` of the check `ui_conn_index < MAX_NUM_ADS_CONNECTIONS` at line 7, i.e. it executes only when that bounds check fails (`ui_conn_index` is NOT within `MAX_NUM_ADS_CONNECTIONS`), so the access is out of bounds by construction on this path.
>
> Reference: CWE-125 (Out-of-bounds Read) | CERT ARR30-C | https://cwe.mitre.org/data/definitions/125.html

**Proposed fix:**
> Add the guard `if (ui_conn_index < 0 || ui_conn_index >= (int)(sizeof(gs_byDsiStartInd) / sizeof(gs_byDsiStartInd[0])))` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

### 3.3 False positive — strict `<` guard keeps the index in range

```c
#define MAX_CPDLC_CONNECTIONS 8
static cpdlc_conn_t gs_cpdlc_conn_tbl[MAX_CPDLC_CONNECTIONS];

void fnCPDLC_Usr_proc_msg_ind(unsigned int ui_conn_index)
{
    if (ui_conn_index < MAX_CPDLC_CONNECTIONS) {
        gs_cpdlc_conn_tbl[ui_conn_index].state = 1;
    }
}
```

**Verdict:** `False positive`

**Comment:**
> The OVERRUN at line 6 in fnCPDLC_Usr_proc_msg_ind() is a false positive. This is because Guard `ui_conn_index < MAX_CPDLC_CONNECTIONS` at line 6 bounds `ui_conn_index` against `MAX_CPDLC_CONNECTIONS`, which tracks the size of `gs_cpdlc_conn_tbl`; the access is in range.

**Proposed fix:**

```text
No fix required.
```

---

### 3.4 Bug — parameter index with no local guard

```c
#define MAX_NUM_ADS_CONNECTIONS 16
static rpt_rec_t gs_ec_rpt_tbl[MAX_NUM_ADS_CONNECTIONS];

void fnadsc_rptmgr_create_fmf_nonpred_dgrps_rpt(unsigned int ui_conn_index)
{
    gs_ec_rpt_tbl[ui_conn_index].b_emrgy_urgy_sts = 1;
}
```

**Verdict:** `Bug`

**Comment:**
> `gs_ec_rpt_tbl[ui_conn_index]` is written at line 4. `gs_ec_rpt_tbl` has 16 elements, but `ui_conn_index` is used without any bounds check. If `ui_conn_index` falls outside the valid range [0, 15], this write touches adjacent memory, corrupting data.
>
> Reference: CWE-125 (Out-of-bounds Read) | CERT ARR30-C | https://cwe.mitre.org/data/definitions/125.html

**Proposed fix:**
> Add the guard `if (ui_conn_index < 0 || ui_conn_index >= (int)(sizeof(gs_ec_rpt_tbl) / sizeof(gs_ec_rpt_tbl[0])))` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

### 3.5 Bug — `memcpy` proceeds after only reporting a fault

```c
#define maxADSCMessageSizeInBytes 32
static struct { unsigned char data[maxADSCMessageSizeInBytes]; } aDSMessage;

void fn(const unsigned char *src, unsigned short data_len)
{
    if (data_len > maxADSCMessageSizeInBytes) {
        fnReportFault(data_len);
    }
    memcpy(aDSMessage.data, src, data_len);
}
```

**Verdict:** `Bug`

**Comment:**
> memcpy at line 6 copies `data_len` bytes into `aDSMessage.data`. A fault is reported at line 5 if the size check fails, but the code proceeds to memcpy anyway after reporting the fault.
>
> Reference: CWE-787 (Out-of-bounds Write) | CERT ARR30-C | https://cwe.mitre.org/data/definitions/787.html

**Proposed fix:**
> Add the guard `if (data_len > sizeof(aDSMessage.data))` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

## 4. INTEGER_OVERFLOW

### 4.1 False positive — operand is range-validated before arithmetic

```c
#define MAX_CONNECTIONS 64

void fn(int si_conn_index)
{
    if (si_conn_index >= 0 && si_conn_index < MAX_CONNECTIONS) {
        unsigned int ui_slot = si_conn_index + 1;
        use(ui_slot);
    }
}
```

**Verdict:** `False positive`

**Comment:**
> The INTEGER_OVERFLOW at line 5 in fn() is not a real defect. The gu**a**rd `si_conn_index >= 0 && si_conn_index < MAX_CONNECTIONS` bounds `si_conn_index` to [0, 63] before the addition, so `ui_slot` remains within the integer type's range. False positive.

**Proposed fix:**

```text
No fix required.
```

---

### 4.2 Needs review — snippet is too small to prove the bound

```c
int compute(int a, int b)
{
    int r = a * b;
    return r;
}
```

**Verdict:** `Needs review`

**Comment:**
> The INTEGER_OVERFLOW at line 3 in compute() needs manual review. The preliminary risk is medium-high — overflows feeding sizes or indices can corrupt the heap. I could not fully verify this because no bounds/null guard for `r` was found before line 3 (it may be in a caller or macro).
>
> Reference: CWE-190 (Integer Overflow or Wraparound) | CERT INT32-C | https://cwe.mitre.org/data/definitions/190.html

**Proposed fix:**

```text
Manual review required.
```

---

### 4.3 Bug — multiplication without an overflow guard

```c
int scale(int count, int factor)
{
    if (count < 0)
        return -1;
    return count * factor;
}
```

**Verdict:** `Bug`

**Comment:**
> At line 4 in scale(), `count * factor` may overflow `int` because no guard proves `factor` is within `INT_MAX / count`. An overflow can feed a later size/index and corrupt memory.
>
> Reference: CWE-190 (Integer Overflow or Wraparound) | CERT INT32-C | https://cwe.mitre.org/data/definitions/190.html

**Proposed fix:**
> Add the guard `if (count != 0 && factor > INT_MAX / count)` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

## 5. FORWARD_NULL

### 5.1 Bug — `malloc` result dereferenced without a NULL check

```c
void f(int n)
{
    int *p = malloc(n * 4);
    *p = 7;
}
```

**Verdict:** `Bug`

**Comment:**
> At line 4, p is dereferenced without a visible null check. If p can be NULL on this path, the access at line 4 crashes; add a null check before first use.
>
> Reference: CWE-476 (NULL Pointer Dereference) | CERT EXP34-C | https://cwe.mitre.org/data/definitions/476.html

**Proposed fix:**
```c
if (!p) {
    return;
}
```

*(The return action follows the function's own convention; `return;` is used here because the function is `void`.)*

---

### 5.2 False positive — pointer is null-checked on the same path

```c
void f(int n)
{
    int *p = malloc(n * 4);
    if (p == NULL) return;
    *p = 7;
}
```

**Verdict:** `False positive`

**Comment:**
> `p` is null-checked at line 4 and the guard covers all paths to the dereference at line 5. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 6. REVERSE_INULL

### 6.1 Bug — dereference before NULL check

```c
void f(int *p)
{
    p->v = 1;
    if (p == NULL) return;
}
```

**Verdict:** `Bug`

**Comment:**
> p->v=1; at line 3 dereferences p with no preceding null check. If p is NULL, the access at line 3 crashes; add a null check before first use.
>
> Reference: CWE-476 (NULL Pointer Dereference) | CERT EXP34-C | https://cwe.mitre.org/data/definitions/476.html

**Proposed fix:**
```c
if (!p) {
    return;
}
```

---

### 6.2 False positive — pointer checked before first use

```c
void f(int *p)
{
    if (p == NULL) return;
    p->v = 1;
}
```

**Verdict:** `False positive`

**Comment:**
> p is checked at line 3 before it is dereferenced at line 4; the null guard precedes first use. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 7. RESOURCE_LEAK

### 7.1 Bug — resource leaked on an early return

```c
int process(int n)
{
    int *p = malloc(n * 4);
    if (n < 0)
        return -1;
    use(p);
    free(p);
    return 0;
}
```

**Verdict:** `Bug`

**Comment:**
> In process() at line 4, `p` is acquired but not released on the early-return path at line 5. Leak on error path → descriptor/memory exhaustion.
>
> Reference: CWE-401 (Missing Release of Memory after Effective Lifetime) | CERT MEM31-C | https://cwe.mitre.org/data/definitions/401.html

**Proposed fix:**
```c
free(p);
```

*(Suggested before the early return, or use the function's existing `goto cleanup` error path.)*

---

### 7.2 False positive — goto cleanup covers all exits

```c
int load(char *buf, int len)
{
    char *tmp = malloc(len);
    if (!tmp) goto cleanup;
    memcpy(tmp, buf, len);
cleanup:
    free(tmp);
    return 0;
}
```

**Verdict:** `False positive`

**Comment:**
> The RESOURCE_LEAK at line 2 in load() is a false positive. This is because goto-cleanup idiom — all exit paths converge to a single release point.

**Proposed fix:**

```text
No fix required.
```

---

## 8. USE_AFTER_FREE

### 8.1 Bug — pointer used after `free()`

```c
void recycle(char *p)
{
    free(p);
    p[0] = 'x';
    log(p);
}
```

**Verdict:** `Bug`

**Comment:**
> At line 3 in recycle(), `p` may be dereferenced after being freed (CWE-416, CERT MEM30-C). `free(p)` occurs at line 2 and no replacement value or effective NULL guard is proven before the later use. That leaves a dangling pointer and the access can corrupt the heap or crash the process.

**Proposed fix:**
```c
free(p); p = NULL;
```

---

### 8.2 False positive — pointer is re-assigned before use

```c
void recycle(char *p)
{
    free(p);
    p = malloc(64);
    p[0] = 'x';
    log(p);
}
```

**Verdict:** `False positive`

**Comment:**
> The USE_AFTER_FREE at line 3 in recycle() is a false positive. `p` is assigned a new value at line 4 before it is used again, so it no longer points into the freed allocation.

**Proposed fix:**

```text
No fix required.
```

---

## 9. UNINIT

### 9.1 Bug — read before any assignment on one path

```c
int total(int a)
{
    int x;
    if (a > 100)
        x = a;
    return x + 1;
}
```

**Verdict:** `Bug`

**Comment:**
> `this local` is read at line 5 in total() before any statement assigns it a definite value. Because the value lives in automatic (stack) storage, the declaration only reserves space in the frame — the bytes already sitting in that slot are never zeroed — so this read yields whatever residual values happen to be there. Once the value is used, behavior is nondeterministic and the residual stack bytes can be disclosed to an observer. The read has no well-defined value, so the outcome is unreproducible. The flagged read is: `x + 1`.
>
> Reference: CWE-457 (Use of Uninitialized Variable) | CERT EXP33-C | https://cwe.mitre.org/data/definitions/457.html

**Proposed fix:**

```text
Manual review required.
```

*(A source-specific patch is withheld only when the analyzer can't name the exact variable/assignment; when it can, it will show `int x = 0;` etc.)*

---

### 9.2 False positive — initialized at declaration

```c
int total(int a)
{
    int x = 0;
    if (a > 100)
        x = a;
    return x + 1;
}
```

**Verdict:** `False positive`

**Comment:**
> The value read at line 5 in total() is given a definite value before it is used: it is explicitly zero-initialized via `= 0` initializer, so no execution path consumes uninitialized storage. Behavior is deterministic. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 10. DIVIDE_BY_ZERO

### 10.1 Bug — divisor not checked

```c
int split(int n, int d)
{
    int r = n / d;
    return r;
}
```

**Verdict:** `Bug`

**Comment:**
> In split() at line 3, division by `d` has no visible non-zero guard (CWE-369, CERT INT33-C). If `d` is zero, this triggers SIGFPE — denial of service.

**Proposed fix:**
> Add the guard `if (d == 0)` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

### 10.2 False positive — divisor checked

```c
int split(int n, int d)
{
    if (d != 0)
        return n / d;
    return 0;
}
```

**Verdict:** `False positive`

**Comment:**
> The DIVIDE_BY_ZERO at line 3 in split() is a false positive. The divisor `d` is explicitly checked for non-zero before the division at line 3.

**Proposed fix:**

```text
No fix required.
```

---

## 11. SIZEOF_MISMATCH

### 11.1 Bug — `sizeof(pointer)` used instead of `sizeof(*ptr)`

```c
void allocate(char *ptr)
{
    char *p = malloc(sizeof(ptr));
}
```

**Verdict:** `Bug`

**Comment:**
> At line 2 in allocate(), `malloc(sizeof(ptr));` takes `sizeof()` of a pointer (or a type that is not the intended element/object). A pointer's size is a small, fixed constant (e.g. 8 on 64-bit targets), so any allocation length or array bound derived from it is only a fraction of the real object. When that value is used in `malloc()`/`calloc()` or as an index limit, the destination is under-allocated and subsequent writes run past the end, corrupting adjacent heap/stack memory (a heap-overflow primitive).
>
> Reference: CWE-467 (Use of sizeof() on a Pointer Type) | CERT ARR01-C | https://cwe.mitre.org/data/definitions/467.html

**Proposed fix:**
```c
malloc(count * sizeof(*ptr));
```

---

### 11.2 False positive — `sizeof(*ptr)` / `sizeof(arr[0])` used

```c
void allocate(char *ptr, int count)
{
    char *p = malloc(count * sizeof(*ptr));
}
```

**Verdict:** `False positive`

**Comment:**
> At line 2 in allocate(), `sizeof()` is taken on the pointee/element (`sizeof(*ptr)` / `sizeof(arr[0])`), which yields the true object size rather than the pointer size. The computed allocation/bound therefore matches the real object, so no under-allocation and no overrun can occur. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 12. NEGATIVE_RETURNS

### 12.1 Bug — negative return used as size/index without validation

```c
int readall(int fd)
{
    char buf[256];
    int n = read(fd, buf, sizeof(buf));
    use(buf, n);
    return n;
}
```

**Verdict:** `Bug`

**Comment:**
> At line 4 in readall(), a signed return value is used as a size or index without first validating it is >= 0. If the call that produced `n` returns a negative error code (e.g. -1), the value is converted to a large unsigned quantity, causing a massive allocation or an out-of-bounds access. Add an explicit `if (result < 0)` check before use.
>
> Reference: CWE-20 (Improper Input Validation) | CERT ERR33-C | https://cwe.mitre.org/data/definitions/20.html

**Proposed fix:**
> Add the guard `if (n < 0)` and reject the invalid value using this module's error convention (early return, goto cleanup, or an error callback). Reviewers should confirm the failure action before applying.

---

### 12.2 False positive — return value checked for negative before use

```c
int readall(int fd)
{
    char buf[256];
    int n = read(fd, buf, sizeof(buf));
    if (n < 0) return -1;
    use(buf, n);
    return n;
}
```

**Verdict:** `False positive`

**Comment:**
> `n` is checked for a negative/error value at line 4 before it is used as a size/index at line 5, so the flagged path cannot carry a negative value into the memory operation. False positive.

**Proposed fix:**

```text
No fix required.
```

---

## 13. CHECKED_RETURN

### 13.1 Bug — safety-critical return value discarded

```c
int pump(int fd)
{
    char buf[256];
    read(fd, buf, sizeof(buf));
    use(buf);
    return 0;
}
```

**Verdict:** `Bug`

**Comment:**
> The CHECKED_RETURN finding at line 3 in pump() is a bug — the return value of read() is discarded, but read() reports errors that are essential for correctness/safety — a failure is silently swallowed.
>
> Reference: CWE-703 (Incorrect Check or Handling of Exceptional Conditions) | CERT EXP12-C | https://cwe.mitre.org/data/definitions/703.html

**Proposed fix:**
> Check the return value of read() and handle the failure (log and/or propagate an error), or cast it to (void) explicitly if ignoring is intentional.

---

### 13.2 Intentional — `(void)` cast documents the ignored return

```c
int flush(void)
{
    (void)fflush(stdin);
    return 0;
}
```

**Verdict:** `Intentional`

**Comment:**
> The CHECKED_RETURN finding at line 2 in flush() is intentional / by design. The return value of fflush() is deliberately ignored — the code documents this with an explicit (void) cast.

**Proposed fix:**

```text
No fix required.
```

---

## 14. ARRAY_VS_SINGLETON

### 14.1 False positive — `&obj[0]` accesses the first element

```c
typedef struct { int x; } obj_t;
void consume(obj_t *ptr)
{
    consume(&ptr[0]);
}
```

**Verdict:** `False positive`

**Comment:**
> `consume(&ptr[0]);` at line 3 in consume() accesses element 0 of `ptr`. `ptr[0]` designates the object itself, and `&ptr[0]` is the same address as `&ptr`, so the access stays inside the single object and cannot touch adjacent memory. False positive.

**Proposed fix:**

```text
No fix required.
```

---

### 14.2 Bug — non-zero index used on a singleton

```c
typedef struct { int x; } obj_t;
void consume(obj_t *ptr)
{
    consume(&ptr[1]);
}
```

**Verdict:** `Bug`

**Comment:**
> `consume(&ptr[1]);` at line 3 treats `ptr` as an array, but only one `ptr` object exists. Index 1 reads/writes 1 object(s) past the singleton — past-the-end memory that belongs to adjacent variables. Declare `ptr` as an array of the needed length or index a real array.
>
> Reference: CWE-468 (Incorrect Pointer Scaling) | CERT ARR37-C | https://cwe.mitre.org/data/definitions/468.html

**Proposed fix:**
> Pass a real array or bound the access to element 0; if the caller contract guarantees single-element access, keep the access and document that contract.

---

## 15. DEADCODE

### 15.1 Bug — block unreachable on every path

```c
void run(void)
{
    if (0)
    {
        old_path();
    }
    new_path();
}
```

**Verdict:** `Bug`

**Comment:**
> The block at line 3 in run() is unreachable on every valid execution path (sits under a constant `0`/`false` condition that can never be true at runtime). Because execution cannot reach it, the guarded action is silently never performed — typically the fingerprint of a mistaken constant, an inverted guard, or a half-removed feature, and it can mask the very logic error that rerouted control away from it.
>
> Reference: CWE-561 (Dead Code) | CERT MSC12-C | https://cwe.mitre.org/data/definitions/561.html

**Proposed fix:**
> Remove the dead block or replace the constant condition with the intended runtime check.

---

### 15.2 Intentional — `#if 0` / `#ifdef NEVER` compiled out

```c
void run(void)
{
#if 0
    old_path();
#endif
    new_path();
}
```

**Verdict:** `Intentional`

**Comment:**
> The block at line 3 in run() is intentionally unreachable (it is excluded by `#if 0` / `#ifdef NEVER`, so the compiler never emits it). It contributes no runtime behavior, so no code change is required; removing it is safe.

**Proposed fix:**

```text
No fix required.
```

---

## 16. NO_BREAK

### 16.1 Intentional — fall-through is annotated

```c
int decode(int c)
{
    switch (c) {
    case 1:
        step_a();
        /* fall through */
    case 2:
        step_b();
        break;
    }
    return 0;
}
```

**Verdict:** `Intentional`

**Comment:**
> The NO_BREAK at line 6 in decode() is intentional / by design. This is because fall-through annotated with FALLTHROUGH / FALLTHRU — intentional control flow documented in source.

**Proposed fix:**

```text
No fix required.
```

---

### 16.2 Bug — missing `break` with no documentation

```c
int decode(int c)
{
    switch (c) {
    case 1:
        step_a();
    case 2:
        step_b();
        break;
    }
    return 0;
}
```

**Verdict:** `Bug`

**Comment:**
> In decode() at line 5, a switch case ends without a break, causing control to fall through to the next case. Unless this is intentional, it will execute unintended code.

**Proposed fix:**
```c
break;
```

---

## 17. CONSTANT_EXPRESSION_RESULT

### 17.1 Bug — constant expression likely hides a logic error

```c
void process(int x)
{
    if (x + 1 == x)
        do_work();
}
```

**Verdict:** `Bug`

**Comment:**
> At line 2 in process(), an expression evaluates to a constant result. This may indicate dead logic, a typo, or a missing variable.
>
> Reference: CWE-570 (Expression is Always False) | CERT MSC12-C | https://cwe.mitre.org/data/definitions/570.html

**Proposed fix:**

```text
Manual review required.
```

---

### 17.2 Intentional — compile-time assertion / `static_assert`

```c
void process(void)
{
    static_assert(sizeof(int) >= 4, "int too small");
}
```

**Verdict:** `Intentional`

**Comment:**
> The CONSTANT_EXPRESSION_RESULT at line 2 in process() is intentional / by design. This is because constant expression is inside a compile-time assertion — by-design invariant check.

**Proposed fix:**

```text
No fix required.
```

---

## 18. SHIFT_OVERFLOW

### 18.1 Bug — shift amount not guarded against the operand width

```c
int shift_it(int value, int amount)
{
    int result = value << amount;
    return result;
}
```

**Verdict:** `Bug`

**Comment:**
> In shift_it() at line 3, a shift operation has no guard against shift amount >= bit-width. In C, shifting by >= width is undefined behavior.
>
> Reference: CWE-758 (Reliance on Undefined, Unspecified, or Implementation-Defined Behavior) | CERT INT34-C | https://cwe.mitre.org/data/definitions/758.html

**Proposed fix:**

```text
Manual review required.
```

*(When the analyzer can resolve the shift amount it will instead give a concrete guard such as `if (amount >= 32) return ERROR;`.)*

---

### 18.2 False positive — shift amount is guarded

```c
int shift_it(int value, int amount)
{
    if (amount < 0 || amount >= 32) return -1;
    return value << amount;
}
```

**Verdict:** `False positive`

**Comment:**
> The SHIFT_OVERFLOW at line 3 in shift_it() is a false positive. The shift amount `amount` is validated against the 32-bit width before the shift.

**Proposed fix:**

```text
No fix required.
```

---

## Summary of commentary style

| Element | Behaviour |
|---|---|
| **Opening** | No tool-speak. Prefers `The <CHECKER> at line N in <fn>() is ...` over `After reviewing ...` |
| **Bug comment** | Root cause → reachable path → impact/corrective action → CWE/CERT reference |
| **False positive** | Concrete code facts that prove safety, ends with `False positive.` |
| **Intentional** | Reads as `intentional / by design`, cites the documenting construct |
| **Needs review** | States the specific unresolved fact, plus risk and this-is-so comment |
| **CWE/CERT footer** | Only on Bug and Needs review, not on False positive/Intentional |
| **Proposed fix** | Pure code patch where possible, or a concise prose instruction; never `<<ERROR_RETURN>>`, `/* report failure here */`, `Suggestion:`, or trailing `// CWE-...` |
