from random import choice
import zipfile
import os
from pathlib import Path
import subprocess
from tempfile import mkdtemp
from threading import Thread
import uuid
import zipfile
import shutil

from flask import Flask, request, send_from_directory, jsonify
from celery import Celery
from celery_worker import make_celery, convert_and_upload
import boto3
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv
from random import choice
import zipfile
import os
import subprocess
from flask import Flask, request, send_from_directory, jsonify
from botocore.exceptions import NoCredentialsError
from dotenv import load_dotenv
import requests

load_dotenv()

app = Flask(__name__)
celery = make_celery()

session = boto3.session.Session(
    aws_access_key_id=os.getenv("AWS_S3_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_S3_SECRET_ACCESS_KEY"),
)
s3_client = session.client("s3")

UPLOAD_FOLDER = "uploads"
RESULTS_FOLDER = "public/results"
ALLOWED_EXTENSIONS = {"zip"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["RESULTS_FOLDER"] = RESULTS_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500MB


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def random_id(length=20):
    allowed_chars = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join([choice(allowed_chars) for _ in range(length)])


@app.route("/generate-upload-url", methods=["POST"])
def generate_upload_url():
    try:
        upload_uuid = str(uuid.uuid4())
        file_name = f"uploads/{upload_uuid}.zip"
        bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        signed_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket_name,
                "Key": file_name,
                "ContentType": "application/zip",
            },
            ExpiresIn=3600,
        )
        # response = s3_client.generate_presigned_post(bucket_name, file_name, Fields=None, Conditions=None, ExpiresIn=3600)
        print(signed_url)
        return jsonify({"uuid": upload_uuid, "url": signed_url, "file_name": file_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/status/<task_id>", methods=["GET"])
def task_status(task_id):
    task = convert_and_upload.AsyncResult(task_id)
    if task.state == "PENDING":
        # Job did not start yet
        response = {"state": task.state, "status": "Pending..."}
    elif task.state != "FAILURE":
        response = {
            "state": task.state,
            "status": task.info.get("log", "No log message available yet."),
        }
        if "result" in task.info:
            response["result"] = task.info["result"]
    else:
        # Something went wrong in the background job
        response = {
            "state": task.state,
            "status": str(task.info),  # this is the exception raised
        }
    return jsonify(response)


@app.route("/convert", methods=["POST"])
def convert_model():
    data = request.get_json()
    if not data or "uuid" not in data:
        return jsonify({"error": "Missing required parameters: uuid"}), 400

    uuid = data["uuid"]
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
    url = f"https://{bucket_name}.s3.amazonaws.com/models/{uuid}.zip"

    # Run the conversion and upload process in a separate thread
    task = convert_and_upload.apply_async(args=[uuid])
    return jsonify({"message": "Conversion started", "task_id": str(task.id)}), 202


@app.route("/upload", methods=["POST"])
def upload_file():
    print(request.files)
    if "file" not in request.files:
        return "No file part", 400

    file = request.files["file"]

    if file.filename == "":
        return "No selected file", 400

    if file and allowed_file(file.filename):
        model_id = random_id()
        upload_path = os.path.join(app.config["UPLOAD_FOLDER"], model_id)
        os.makedirs(upload_path, exist_ok=True)
        file.save(os.path.join(upload_path, file.filename))

        # Unzip the file
        with zipfile.ZipFile(os.path.join(upload_path, file.filename), "r") as zip_ref:
            zip_ref.extractall(upload_path)

        # Convert the model
        conversion_process = subprocess.run(
            [
                "tensorflowjs_converter",
                os.path.join(upload_path, "generator"),
                os.path.join(app.config["RESULTS_FOLDER"], model_id),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        if conversion_process.returncode != 0:
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": "Conversion failed",
                        "output": conversion_process.stdout.decode(),
                    }
                ),
                200,
            )

        # Zip the results
        zip_process = subprocess.run(
            [
                "zip",
                "-r0",
                f'{os.path.join(app.config["RESULTS_FOLDER"], model_id)}.zip',
                os.path.join(app.config["RESULTS_FOLDER"], model_id),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        if zip_process.returncode != 0:
            return (
                jsonify(
                    {
                        "status": "error",
                        "error": "Zipping failed",
                        "output": zip_process.stdout.decode(),
                    }
                ),
                200,
            )

        return (
            jsonify(
                {
                    "status": "success",
                    "id": model_id,
                    "output": conversion_process.stdout.decode(),
                }
            ),
            200,
        )

        return model_id, 200

    return "File not allowed", 400


@app.route("/download/<model_id>", methods=["GET"])
def download_file(model_id):
    return send_from_directory(
        app.config["RESULTS_FOLDER"], f"{model_id}.zip", as_attachment=True
    )


@app.route("/", methods=["GET"])
def index():
    return send_from_directory("public", "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, debug=True)
