from random import choice
import zipfile
from flask import Flask, request, send_from_directory, jsonify
import os
import subprocess

app = Flask(__name__)

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
                        "error": "Conversion failed",
                        "output": conversion_process.stdout.decode(),
                    }
                ),
                200,
            )

        # Zip the results
        subprocess.run(
            [
                "zip",
                "-r0",
                f'{os.path.join(app.config["RESULTS_FOLDER"], model_id)}.zip',
                os.path.join(app.config["RESULTS_FOLDER"], model_id),
            ]
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
    app.run(host="0.0.0.0", port=5000)
