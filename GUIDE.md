# Integrated Institution Complaint Monitoring and Status Dashboard
### Beginner guide (Hinglish) + working prototype

Is guide ke saath poora chalta hua prototype hai (Python Flask + SQLite + plain JavaScript).
Har section ke saath saaf likha hai ki kya **implemented** hai (code mein hai, test hua) aur kya sirf **proposed** hai (idea, abhi code nahi).

> **Honesty note:** Saara data **synthetic** hai. AICTE ke kisi internal database ya API se connection **nahi** hai. Deadlines (SLA) aur statuses **demo placeholders** hain. "AI" ke naam par jo hai, wo abhi **rule-based scoring** hai, koi trained ML model nahi.

---

## 1. Problem statement simple Hinglish mein

AICTE ke paas technical colleges ke baare mein shikayatein aati hain (students, faculty, aur dusre log se). Ye shikayatein alag-alag departments handle karte hain, jaise **RB (Regulation Bureau)** aur **PGRC (Public Grievance Redressal Cell)**.

Problem ye hai ki **ek hi college** ki shikayatein RB ke paas bhi ho sakti hain aur PGRC ke paas bhi, aur dono ko ek-doosre ka pata nahi hota. Isse kaam double hota hai, deri hoti hai, aur kabhi-kabhi alag-alag action ho jaate hain.

**Humein banana hai:** ek single-window dashboard jahan authorised AICTE officials:
1. Saari complaints ek jagah dekh saken
2. Dekh saken ki kaun sa Bureau/Cell abhi handle kar raha hai
3. Har complaint ki poori history track kar saken
4. **Aise cases pakad saken jahan multiple departments same college par kaam kar rahe hain**
5. Pending, overdue, disposed cases monitor kar saken, reports nikal saken, alerts dekh saken

---

## 2. Asli problem aur root causes

| Root cause | Matlab | Natija |
|---|---|---|
| Alag-alag systems / registers | RB aur PGRC ka data alag jagah hai | Koi ek "single source of truth" nahi |
| Common identifier nahi | Complaint IDs har department ki alag hoti hain | College-wise combined view nahi banta |
| Real-time visibility nahi | Status jaanne ke liye phone/email/file | Deri aur confusion |
| Koi overlap check nahi | Same college par do departments ko pata nahi | Duplicate ya conflicting action |
| Deadline tracking weak | Kaunsi complaint kab tak nipatani hai, ye manually dekhna padta hai | Cases overdue ho jaate hain |
| Transfer history kho jaati hai | Case ek department se doosre mein gaya, record nahi | Accountability kam |

**Core insight:** problem "complaint register karna" nahi hai (wo already hota hai). Problem hai **departments ke beech ki visibility aur coordination**. Isliye is project ka sabse important feature **overlap detection + coordination workflow** hai.

---

## 3. Target users aur unki difficulties

| User | Difficulty abhi | Dashboard mein kya milta hai |
|---|---|---|
| **Officer (RB / PGRC / other cell)** | Pata nahi doosre department ne same college par kya kiya | Case details, overlap alert, coordination remarks |
| **Supervisor / Head** | Workload aur overdue cases ka ek jagah view nahi | Dashboard, alerts, reports, CSV export |
| **Regional office (viewer)** | Apne region ke colleges ka status nahi dikhta | Read-only view, region filter, sensitive data masked |
| **Competent Authority / Management** | Decision ke liye data scattered | Consolidated reports, ageing, disposal rate |
| **Admin (IT cell)** | Access control aur audit | User list, audit log, settings |

Prototype mein ye 4 roles implemented hain: `admin`, `supervisor`, `officer` (apne Bureau/Cell ke saath), `viewer`.

---

## 4. Proposed solution aur uska working

**Ek web dashboard** jo saari complaints ko ek **common format** mein rakhta hai. Har complaint apni original ID (`source_ref`) aur original department (`source_system`) ke saath save hoti hai.

Working step by step:

1. Complaints common format mein database mein aati hain (prototype mein synthetic data seed hota hai)
2. Har institution ki **AICTE Permanent ID** se unki complaints jud jaati hain
3. **Overlap engine** har institution ki complaints ke pairs compare karta hai, score deta hai, aur reasons ke saath "Potential overlap" flag lagata hai
4. Official alert kholta hai, dono cases **side by side** dekhta hai
5. Official **Confirm (link)** ya **Dismiss** karta hai, aur remarks likhta hai. Dono departments **coordination remarks** aur decision record karte hain
6. Har action history mein save hota hai (kisne, kab, kya)
7. Alerts page overdue / approaching / no-recent-action / overlap dikhata hai
8. Reports page se statistics aur CSV export (sirf supervisor/admin)

**Sabse important rule:** system sirf **flag** karta hai. Wo kabhi complaints ko **merge, close, ya duplicate declare nahi karta**. Decision hamesha official ka hota hai. Ye tests se verify kiya gaya hai (section 14).

---

## 5. Unique selling points aur innovative features

| Feature | Status |
|---|---|
| Cross-Bureau overlap detection with **explainable score** (har flag ke saath reasons) | Implemented |
| Alag shabdon mein likhi same shikayat bhi pakadna ("fewer faculty" vs "teachers not available") | Implemented (chhota synonym map) |
| Same external reference (jaise portal reference) se link pakadna | Implemented |
| **Side-by-side compare view** jisme matching fields highlight hote hain | Implemented |
| Potential / Confirmed / Dismissed ka alag status (galti se "duplicate" nahi maana jaata) | Implemented |
| Coordination thread + decision tracking, jo dono cases ki history mein bhi likha jaata hai | Implemented |
| Permissions **server par** enforce, complainant contact masked | Implemented |
| Audit log (login, actions, exports) | Implemented |
| Configurable SLA / thresholds (hardcoded deadline nahi) | Implemented (settings API + table; UI mein sirf dikhta hai) |
| Institution profile jahan ek nazar mein "PGRC ke 2 case, RB ka 1, 1 overlap, 1 overdue" dikhe | Implemented |
| ML / embeddings se semantic matching | **Proposed** |
| Hindi / mixed-language complaint text support | **Proposed** |
| Live integration with AICTE systems / CPGRAMS | **Proposed** (authorisation chahiye) |

---

## 6. AI/ML integration: kya karega aur kyun chahiye

### Abhi implemented (rule-based, koi ML model nahi)

`overlap.py` mein transparent scoring hai:

| Rule | Points |
|---|---|
| Same AICTE Permanent ID (gate: iske bina flag nahi) | +30 |
| Same category (related category: +10) | +20 |
| Same subcategory | +15 |
| Description similarity (cosine similarity, 0 se 1) | 0 se +25 |
| Dates 30 din ke andar (90 din ke andar +5) | +10 |
| Same external reference | +15 |
| **Flag threshold** (settings se badal sakte hain) | 65 |

Text similarity ke liye text ko lowercase karte hain, stopwords hataate hain, plural simple karte hain, aur synonyms map karte hain (`teachers` ko `faculty`, `vacant` ko `shortage`). Phir do descriptions ka **cosine similarity** nikalte hain. Ye classical NLP hai, "AI model" nahi.

**Kyun rule-based?** Explainable hai. Government setting mein officer ko ye jaanna zaroori hai ki system ne kyun flag kiya. Aur beginner ke liye samajhna aur debug karna aasaan hai.

### Proposed (abhi code nahi)

| Idea | Fayda | Dhyan rakhne wali baat |
|---|---|---|
| Sentence embeddings (jaise multilingual sentence-transformers) | Alag wording aur Hindi/English mix bhi match ho | Real complaint data par evaluate karna zaroori, privacy aur hosting ka sawal |
| Threshold tuning with labelled pairs | False alarms kam | Officials se labelled examples chahiye |
| Complaint auto-categorisation suggestion | Time bachta hai | Sirf suggestion, official confirm kare |

**AI ke liye safety rules (design choice):** AI kabhi complaint ki sachchai decide nahi karega, kabhi close/dispose nahi karega, aur score kabhi "duplicate proof" nahi maana jaayega.

---

## 7. Tech stack: frontend, backend, database, APIs

| Layer | Choice | Kyun |
|---|---|---|
| Frontend | HTML + CSS + plain JavaScript (hash routing) | Koi build step nahi, beginner ke liye seedha |
| Backend | Python 3 + Flask | Chhota, padhne mein aasaan |
| Database | SQLite (ek file: `data/complaints.db`) | Install nahi karna padta. Production ke liye PostgreSQL proposed |
| Auth | Password hash (Werkzeug) + session token | Demo ke liye kaafi |
| Tests | Python `unittest` | Extra install nahi |
| Charts | CSS bars | Offline chalta hai, library nahi |

### API endpoints (sab implemented)

| Endpoint | Kaam |
|---|---|
| `POST /api/login`, `POST /api/logout` | Login / logout |
| `GET /api/meta` | Bureaus, statuses, categories, definitions |
| `GET /api/dashboard` | Cards + chart data |
| `GET /api/complaints` (filters: q, bureau, category, status, region, date_from, date_to, overdue) | Searchable list |
| `GET /api/complaints/<id>` | Case details + history + overlaps |
| `POST /api/complaints/<id>/action` | update_status, transfer, escalate, assign, remark, correct |
| `GET /api/institutions`, `GET /api/institutions/<id>` | Institution profile |
| `GET /api/overlaps`, `GET /api/overlaps/<id>` | Alerts aur side-by-side data |
| `POST /api/overlaps/detect` | Detection dobara chalao |
| `POST /api/overlaps/<id>/review` | Confirm ya dismiss (remarks zaroori) |
| `POST /api/overlaps/<id>/coordination` | Coordination remark + decision |
| `GET /api/alerts` | Overdue, approaching, no-recent-action, overlaps, coordination |
| `GET /api/reports/<kind>` (`?format=csv`) | 8 reports; CSV sirf supervisor/admin |
| `GET /api/users`, `GET /api/audit` | Sirf admin |
| `GET/PUT /api/settings` | Settings dekhna / badalna (badalna sirf admin) |

---

## 8. System architecture aur user workflow

```
 Browser (HTML/CSS/JS)                 Flask server (app.py)                 SQLite
 ┌──────────────────────┐   JSON      ┌──────────────────────────┐        ┌───────────────┐
 │ Login                │  ───────►   │ Auth + role checks       │  ───►  │ institutions  │
 │ Dashboard            │  Bearer     │ REST API                 │        │ complaints    │
 │ Complaints / Case    │  token      │ Reports + CSV            │        │ history       │
 │ Institutions         │  ◄───────   │                          │  ◄───  │ overlap_alerts│
 │ Overlap / Coordination│            │ overlap.py (scoring)     │        │ coord. notes  │
 │ Alerts / Reports     │             │ seed.py (synthetic data) │        │ users, audit  │
 └──────────────────────┘             └──────────────────────────┘        └───────────────┘
                                                   ▲
                                                   │ (PROPOSED, not built)
                                      Adapters for authorised AICTE systems
```

**Officer workflow (overlap):**
1. Login, Dashboard par "Potential overlaps: 31" dekha
2. Alert #1 kholi: C101 (PGRC) aur C205 (RB), College A, score 85
3. "Why flagged" mein reasons padhe, side-by-side compare kiya
4. Coordination remark likha ("RB will lead") aur decision select kiya
5. Confirm and link cases dabaya, remarks ke saath
6. Dono cases ki history mein ye entries apne aap aa gayi

---

## 9. Database schema aur sample data

Schema `db.py` mein hai. Main tables:

| Table | Mukhya columns |
|---|---|
| `institutions` | permanent_id (PK), name, address, city, state, region, institution_type |
| `complaints` | complaint_id (PK), source_ref, source_system, institution_id, category, subcategory, description, date_received, bureau, assigned_officer, status, last_action, last_action_date, next_action, expected_disposal_date, sla_days, external_ref, complainant_name, complainant_contact |
| `complaint_history` | complaint_id, ts, action, from_status, to_status, from_bureau, to_bureau, actor, actor_bureau, remarks |
| `overlap_alerts` | complaint_a, complaint_b, institution_id, score, reasons (JSON), status (Potential/Confirmed/Dismissed), reviewed_by, review_remarks, coordination_status |
| `complaint_links` | complaint_a, complaint_b, alert_id, linked_by, linked_at |
| `coordination_notes` | alert_id, ts, username, bureau, remark, decision |
| `sla_rules`, `settings` | Configurable deadlines aur thresholds |
| `users`, `sessions`, `audit_log` | Access control aur audit |

**Design choices:** purani bureau/status kabhi overwrite karke gayab nahi hoti. Har badlav `complaint_history` mein nayi row banta hai. Original complaint ID `source_ref` mein safe rehti hai.

### Sample data (synthetic)

| ID | Institution | Bureau | Category / Subcategory | Status | Received | Due (demo SLA) |
|---|---|---|---|---|---|---|
| C101 | SYN-00001 (College A) | PGRC | Faculty / Faculty shortage | Under Process | 2026-09-17 | 2026-11-01 |
| C205 | SYN-00001 (College A) | RB | Faculty / Faculty shortage | Under Process | 2026-09-26 | 2026-11-10 |
| C310 | SYN-00001 (College A) | PGRC | Fee and finance / Fee refund | Pending | 2026-10-15 | 2026-11-14 |
| C412 | SYN-00002 (College B) | RB | Approval norms / Intake beyond approval | Under Process | 2026-06-29 | 2026-08-28 (overdue) |

Total: 40 synthetic institutions, 181 complaints (11 haath se banaye scenarios + 170 random), 8 users. Permanent ID ka format `SYN-xxxxx` sirf demo ke liye hai. Asli AICTE ID format confirm karna baaki hai.

Demo scenarios jo seed mein jaan-boojh kar daale gaye:
- **College A:** C101 aur C205 overlap, C310 alag issue (flag nahi hona chahiye)
- **College C:** alag shabd, same issue (C520/C521)
- **College D:** same external reference, alag wording (C600/C601)
- **College E:** same institution, alag issues (C700/C701, flag nahi hona chahiye)
- **College B:** overdue case

---

## 10. UI/UX design aur website pages

Design direction: shaant, official dashboard. Dark ink sidebar, light content area. **Ek hi cheez par zor:** overlap compare view (amber border, dashed divider, matching rows highlighted). Baaki sab sanyamit rakha hai. Persistent banner "Synthetic demo data" har page par dikhta hai.

| Page | Route | Kya hai |
|---|---|---|
| Login | (pehla screen) | Demo account buttons |
| Dashboard | `#/dashboard` | 8 cards, Bureau/status/region bars, top institutions |
| All complaints | `#/complaints` | Search + 8 filters, table |
| Case details | `#/complaints/C101` | Saari fields, actions, timeline, related alerts |
| Institutions | `#/institutions`, `#/institutions/SYN-00001` | Search aur institution profile |
| Overlap detection | `#/overlaps`, `#/overlaps/1` | Alert list aur side-by-side review |
| Coordination centre | `#/coordination` | Alerts jahan decision baaki hai |
| Alerts | `#/alerts` | Overdue, approaching, no recent action, overlaps |
| Reports | `#/reports/<type>` | 8 reports + CSV export |
| Users and settings | `#/users` | Users, audit log (admin), SLA table, definitions |

Basic accessibility: keyboard focus visible, labels on inputs, responsive layout, reduced-motion respect. Formal accessibility audit **nahi** hui.

---

## 11. Step-by-step development roadmap

| Step | Kaam | Status |
|---|---|---|
| 1 | Requirements, common complaint format, statuses define karna | Done |
| 2 | Database schema (`db.py`) | Done |
| 3 | Synthetic data (`seed.py`) | Done |
| 4 | Overlap engine (`overlap.py`) + unit tests | Done |
| 5 | REST API (`app.py`) with roles | Done |
| 6 | Frontend pages (`static/`) | Done |
| 7 | API tests, UI render check | Done |
| 8 | AICTE se confirm karna: complaint types ka routing, official statuses, deadlines, roles | **Baaki (AICTE input chahiye)** |
| 9 | Authorised data integration (adapters) | **Baaki** |
| 10 | Security hardening (HTTPS, MFA, rate limiting, backups, CERT-In guidelines check) | **Baaki** |
| 11 | Attachments, email/SMS notifications, scheduled detection | **Baaki** |
| 12 | Embedding-based matching, threshold tuning on labelled data | **Baaki** |

---

## 12. Complete working code, file by file

```
complaint-dashboard/
├── app.py            Flask backend: auth, API, reports
├── config.py         Bureaus, statuses, categories, SLA placeholders, settings
├── db.py             SQLite schema + connection
├── overlap.py        Overlap scoring engine (rule-based)
├── seed.py           Synthetic data generator
├── requirements.txt  Flask
├── static/
│   ├── index.html    Page shell
│   ├── style.css     Styling
│   └── app.js        Frontend logic (all pages)
├── tests/
│   ├── test_overlap.py   8 unit tests
│   └── test_api.py       16 API tests
├── GUIDE.md          Ye guide
└── README.md         Quick start
```

Poora code in files mein hai. Zip download link chat mein diya gaya hai. Har file ke upar comments Hinglish mein hain.

---

## 13. VS Code mein run karne ke instructions

**Pehle chahiye:** Python 3.10 ya naya (python.org se install karo. Windows par installer mein "Add Python to PATH" tick karo), aur VS Code.

1. Zip extract karo. VS Code mein **File > Open Folder** se `complaint-dashboard` kholo.
2. **Terminal > New Terminal** kholo.
3. Virtual environment banao (isse libraries is project tak limited rehti hain):
   - Windows: `python -m venv venv` phir `venv\Scripts\activate`
   - Mac/Linux: `python3 -m venv venv` phir `source venv/bin/activate`
4. Library install karo: `pip install -r requirements.txt`
5. Server chalao: `python app.py` (Windows par `python` na chale to `py app.py`)
   - Pehli baar chalane par database apne aap ban jaata hai aur synthetic data load hota hai.
6. Browser mein kholo: **http://127.0.0.1:5000**
7. Demo login: login screen ke buttons dabao ya type karo. Password sabka **demo123**.

| Username | Role |
|---|---|
| `admin` | Admin |
| `head.office` | Supervisor |
| `a.sharma` | PGRC officer |
| `r.verma` | RB officer |
| `m.iyer` | Other-cell officer |
| `regional.viewer` | Viewer |

**Data reset karna ho:** `python seed.py` (purana database delete karke naya banata hai).

**Common errors:**
- `ModuleNotFoundError: flask` ka matlab virtual environment activate nahi hai ya `pip install` nahi chala.
- Port 5000 busy hai to `app.py` ke last line mein `port=5001` karo.

---

## 14. Testing process aur sample outputs

Tests chalane ka command: `python -m unittest -v`

**Asli output (is build par chalaya gaya, 27 Oct 2026):**

```
Ran 24 tests in 2.800s

OK
```

Jo tests hain (24, sab pass):

| Kya check hota hai | Test |
|---|---|
| Problem statement ka example: C101 + C205 flag ho | `test_problem_statement_example_is_flagged`, `test_c101_c205_flagged_and_c310_not` |
| Same institution, alag issue flag **na** ho | `test_same_institution_different_issue_is_not_flagged` |
| Alag wording, same issue pakde | `test_different_wording_same_issue_is_flagged` |
| Same external reference se flag | `test_same_external_reference_is_flagged` |
| Detection complaints ko **badalta nahi** | `test_detection_never_changes_complaints` |
| Viewer / doosre bureau ka officer action nahi kar sakta | `test_viewer_cannot_act`, `test_officer_of_other_bureau_cannot_act` |
| Complainant contact masked | `test_contact_details_masked_for_viewer` |
| Dispose ke liye remarks zaroori, disposed case officer reopen nahi kar sakta | `test_dispose_requires_remarks_and_is_recorded` |
| Transfer mein purani history safe | `test_transfer_keeps_history` |
| Dismissed alert dobara detection se wapas nahi aata | `test_dismiss_requires_remarks_and_survives_rerun` |
| Confirm karne par link bane, records merge **na** hon | `test_confirm_links_without_merging` |
| CSV export sirf supervisor/admin ko, audit mein entry | `test_csv_export_restricted_and_audited` |
| Dashboard ke numbers consistent | `test_dashboard_numbers_are_consistent` |

**Seed data par overlap detection ka asli output (College A):**

```
C101 + C205  score 85
  Same AICTE Permanent ID (+30)
  Same category: Faculty (+20)
  Same subcategory: Faculty shortage (+15)
  Description similarity 38% (+10)
  Received 9 days apart (+10)

C101 vs C310 -> score 44, NOT flagged (alag issue)
C700 vs C701 -> score 35, NOT flagged
```

Seed ke baad: 181 complaints aur 31 potential overlaps. Inmein 3 haath se banaye scenarios ke hain (C101/C205, C520/C521, C600/C601) aur 28 random data se bane hain.

**Seed ke baad dashboard (27 Oct 2026):** Total 181, Pending 36, Under process 61, Disposed 62, Transferred 14, Escalated 8, Overdue 53, Potential overlaps 31. Overdue ka number aaj ki date par depend karta hai.

**Kya test NAHI hua:** real AICTE data, bahut bade datasets (performance), load testing, security penetration testing, alag browsers (sirf headless Chromium par render check hua, console errors nahi aaye), accuracy of overlap detection real complaints par. Overlap threshold (65) synthetic data par chuna gaya hai. Real data par iska precision/recall **maloom nahi**.

---

## 15. Limitations, challenges, aur future scope

### Limitations (honest list)

| Limitation | Detail |
|---|---|
| Synthetic data | Koi real integration nahi. "Real-time" ka matlab abhi hai har page load par database se fresh calculation. Live push ya sync nahi |
| Overlap detection chalta kab hai | Seed ke waqt aur "Re-run detection" button par. Nayi complaint aate hi apne aap nahi (scheduled job nahi) |
| Rule-based matching | Synonym list chhoti aur sirf English. Complex ya Hindi text miss ho sakta hai, aur kabhi galat flag bhi |
| Placeholder rules | SLA days, statuses, bureaus, regions, categories sab demo hain. AICTE ke official rules se replace karne honge |
| Attachments | Supporting documents upload **implemented nahi** |
| Notifications | Alerts sirf app ke andar. Email/SMS **nahi** |
| Users | User create/edit ka UI nahi. Settings sirf API se badalte hain |
| Security | Demo level. HTTPS, MFA, rate limiting, CSRF review, backups, encryption at rest, retention policy **nahi** hain. Production se pehle CERT-In guidelines aur data-protection requirements check karni hongi |
| Scale | SQLite aur har institution ke andar pair comparison. Chhote data ke liye theek, bade ke liye PostgreSQL aur indexing chahiye |
| Pagination | List mein max 200 rows |
| Accessibility | Basic. Formal audit nahi |

### Challenges (asli duniya mein)

- Alag departments ka data alag formats mein hoga. Adapter layer aur data cleaning chahiye
- Permanent ID har complaint mein sahi bhari hogi, ye assumption hai
- Kaun transfer/dispose kar sakta hai, ye AICTE ke official rules se tay hoga
- Privacy: complaints mein personal details hoti hain. Role-based access aur retention policy official guidance se banegi

### Future scope

1. AICTE se workflow, statuses, deadlines aur roles confirm karna (sabse pehla kadam)
2. Authorised integration (agar APIs/data-sharing milta hai)
3. Embedding-based matching aur labelled data se tuning
4. Attachments, email/SMS reminders, scheduled detection
5. PostgreSQL, HTTPS, MFA, backups, full audit
6. Hindi aur regional language support
7. Regional office specific views

---

## 16. Hackathon presentation script aur judge Q&A

### 3-minute script

**(0:00) Problem.** "AICTE mein ek hi college ki shikayatein RB ke paas bhi aati hain aur PGRC ke paas bhi. Dono ko ek-doosre ka pata nahi. Natija: duplicate kaam, deri, aur kabhi conflicting action."

**(0:30) Solution.** "Humne ek single-window dashboard banaya hai jo sab Bureaus/Cells ki complaints ko ek common format mein laata hai. Har college ki AICTE Permanent ID se uski saari complaints ek profile mein dikhti hain."

**(1:00) Demo, dashboard.** "Yahan 8 cards hain: total, pending, under process, disposed, transferred, escalated, overdue aur potential overlaps."

**(1:20) Demo, overlap (core).** "College A ka example. PGRC ke paas C101 hai, RB ke paas C205. Dono faculty shortage ki hain. System ne inhe flag kiya, score 85, aur **wajah bhi dikhayi**: same Permanent ID, same category, same subcategory, similar description. Dhyan dein, C310 jo fee refund ki hai, flag **nahi** hui kyunki issue alag hai."

**(2:00) Coordination.** "Officer dono cases side-by-side dekhta hai, coordination remark likhta hai, 'RB lead karega' decision record karta hai, aur cases ko link ya dismiss karta hai. System khud kabhi merge ya close nahi karta. Decision hamesha official ka."

**(2:25) Trust.** "Har action ki history, har export ka audit, complainant ki details sirf authorised users ko. Deadlines hardcoded nahi, configurable hain, kyunki alag complaint types ka alag process ho sakta hai."

**(2:45) Honesty and next.** "Ye prototype synthetic data par hai, 24 automated tests pass hote hain. Next step: AICTE se official workflow aur deadlines confirm karna, aur authorised data integration."

### Judge Q&A

**Q1. Kya ye real AICTE data use karta hai?**
Nahi. Saara data synthetic hai aur UI par har page par label hai. AICTE ke internal systems ka access nahi hai, to humne common format bana kar adapter-based integration ka design rakha hai. Live integration abhi proposed hai.

**Q2. Isme AI kahan hai?**
Honestly, abhi rule-based scoring hai: institution match, category, text similarity (cosine), dates, aur external reference. Isme koi trained ML model nahi hai. Humne jaan-boojh kar explainable approach chuni. Embeddings aur tuning future scope hai.

**Q3. Overlap detection galat flag kare to?**
Isliye system sirf flag karta hai. Official confirm ya dismiss karta hai, remarks ke saath, aur dismissed alert dobara detection se wapas nahi aata. Aur flag ke saath reasons dikhte hain.

**Q4. Kitna accurate hai?**
Synthetic scenarios par design ke hisaab se kaam karta hai (tests pass). Real data par precision/recall humne measure **nahi** kiya, aur threshold 65 synthetic data par chuna gaya hai. Real data milne par labelled examples se tune karenge.

**Q5. Deadlines kaise tay hote hain?**
SLA table se, category ke hisaab se, aur ye configurable hai. Abhi ki values demo placeholders hain. Official timelines milne par replace karenge. Hum sab complaints par ek hi deadline nahi lagaate.

**Q6. Duplicate ko merge kyun nahi karte?**
Kyunki do complaints same college par hone ka matlab ye nahi ki wo same allegation hain. Merge ya close karna official decision hai. Hum records alag rakhte hain aur sirf link karte hain.

**Q7. Privacy aur security?**
Implemented: password hashing, token sessions, role checks server par, contact masking, controlled CSV export, audit log. Production ke liye abhi baaki: HTTPS, MFA, rate limiting, encryption at rest, retention policy, aur CERT-In/data-protection requirements ki official verification.

**Q8. Ek department doosre ka case dekh sakta hai?**
Haan, view kar sakta hai (consolidated view ka yahi maksad hai), lekin action sirf responsible Bureau/Cell ke officers ya supervisor kar sakte hain. Contact details bhi restricted hain.

**Q9. Scale kaise hoga?**
Abhi SQLite aur chhota data. Production ke liye PostgreSQL, indexing, aur scheduled/batched detection. Comparison sirf ek institution ke andar hota hai, to poore dataset par O(n squared) nahi chalta.

**Q10. Real-time kaise hai?**
Har page load par database se fresh numbers aate hain. True live push ya background sync abhi nahi hai. Wo future scope hai jab data sources connect honge.

**Q11. Transfer ke baad purana record?**
Safe rehta hai. Transfer par nayi history entry banti hai (from bureau, to bureau, reason, kaun, kab). Test se verify hua hai.

**Q12. Aapne kya build kiya aur kya nahi?**
Built: dashboard, complaints table with filters, institution profiles, case details with history, overlap detection with review and coordination, alerts, 8 reports, roles, audit. Not built: attachments, notifications, live integration, ML matching, production security hardening.
