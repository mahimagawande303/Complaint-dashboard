# Institution Complaint Monitor (prototype)

Synthetic-data prototype of a centralized complaint dashboard with cross-Bureau overlap detection.
Full explanation (Hinglish): see GUIDE.md

## Run
    python -m venv venv
    venv\Scripts\activate          (Mac/Linux: source venv/bin/activate)
    pip install -r requirements.txt
    python app.py
Open http://127.0.0.1:5000  - demo password for every account: demo123
(admin, head.office, a.sharma, r.verma, m.iyer, regional.viewer)

## Test
    python -m unittest -v

## Reset data
    python seed.py
