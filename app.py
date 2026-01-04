from flask import Flask, request, jsonify
from flask_cors import CORS
import face_recognition
import numpy as np
import base64
import cv2
import mysql.connector
from datetime import datetime
import schedule
import time
import threading

app = Flask(__name__)
CORS(app)

# ===== MYSQL CONNECTION =====
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="krishna123",
    database="facetrack"
)
cursor = db.cursor()


@app.route("/")
def home():
    return "FaceTrack Backend Running Successfully"


# ===== REGISTER FACE =====
@app.route("/register", methods=["POST"])
def register_student():

    data = request.json
    roll_no = data["roll_no"]
    name = data["name"]
    image_data = data["image"]

    img_bytes = base64.b64decode(image_data.split(",")[1])
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    faces = face_recognition.face_locations(img)
    encodings = face_recognition.face_encodings(img, faces)

    if len(encodings) == 0:
        return jsonify({"status": "fail", "message": "No face detected"})

    encoding_str = ",".join(map(str, encodings[0]))

    cursor.execute(
        "UPDATE students SET student_name=%s, face_encoding=%s WHERE roll_no=%s",
        (name, encoding_str, roll_no)
    )
    db.commit()

    return jsonify({"status": "success", "message": "Face registered successfully"})


# ===== ATTENDANCE API =====
@app.route("/attendance", methods=["POST"])
def attendance():

    print("Attendance API Called")

    # ---------- TEST MODE (ALLOWS ANY TIME) ----------
    now = datetime.now().time()
    hour = datetime.now().hour
    session = "MORNING" if hour < 12 else "AFTERNOON"

    # ---------- READ IMAGE ----------
    data = request.json
    image_data = data["image"]

    img_bytes = base64.b64decode(image_data.split(",")[1])
    np_arr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    faces = face_recognition.face_locations(img)
    encodings = face_recognition.face_encodings(img, faces)

    if len(encodings) == 0:
        return jsonify({"message": "No face detected"})

    face_enc = encodings[0]

    # ---------- MATCH FACE ----------
    cursor.execute("SELECT student_id, roll_no, face_encoding FROM students")
    students = cursor.fetchall()

    best_match = None
    best_distance = 0.45

    for student_id, roll_no, stored_enc in students:

        if stored_enc is None:
            continue

        stored_enc = np.fromstring(stored_enc, sep=",")
        distance = face_recognition.face_distance([stored_enc], face_enc)[0]

        if distance < best_distance:
            best_distance = distance
            best_match = (student_id, roll_no)

    if best_match is None:
        return jsonify({"message": "Face not recognized"})

    student_id, roll_no = best_match

    # ---------- UPDATE / INSERT ATTENDANCE ----------
    cursor.execute(
        "SELECT attendance_id FROM attendance "
        "WHERE student_id=%s AND date=CURDATE() AND session=%s",
        (student_id, session)
    )
    row = cursor.fetchone()

    if row:
        cursor.execute(
            "UPDATE attendance SET status='Present', time=CURTIME() "
            "WHERE attendance_id=%s",
            (row[0],)
        )
    else:
        cursor.execute(
            "INSERT INTO attendance (student_id, date, time, status, session) "
            "VALUES (%s, CURDATE(), CURTIME(), 'Present', %s)",
            (student_id, session)
        )

    db.commit()

    return jsonify({"message": f'Attendance marked for {roll_no} ({session})'})


# ===== AUTO ABSENT (DISABLED FOR TESTING) =====
# schedule.every().day.at("08:31").do(mark_morning_absent)
# schedule.every().day.at("13:31").do(mark_afternoon_absent)


def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)


threading.Thread(target=run_scheduler, daemon=True).start()


# ===== REPORT API =====
@app.route("/report")
def report():
    date = request.args.get("date")

    cursor.execute("""
        SELECT s.roll_no, s.student_name, a.session, a.status, a.time
        FROM attendance a
        JOIN students s ON a.student_id = s.student_id
        WHERE a.date = %s
        ORDER BY s.roll_no, a.session
    """, (date,))

    rows = cursor.fetchall()

    result = []
    for r in rows:
        result.append({
            "roll_no": r[0],
            "name": r[1],
            "session": r[2],
            "status": r[3],
            "time": str(r[4]) if r[4] else None
        })

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
