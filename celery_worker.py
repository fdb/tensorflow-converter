import os
from pathlib import Path
import subprocess
from tempfile import mkdtemp
from threading import Thread
import uuid
import zipfile
import shutil
from time import sleep

import boto3
from botocore.exceptions import NoCredentialsError
from celery import Celery, current_task
from dotenv import load_dotenv
import requests

load_dotenv()


def make_celery(app_name=__name__):
    return Celery(
        app_name, backend=os.getenv("REDIS_URL"), broker=os.getenv("REDIS_URL")
    )


celery = make_celery()


@celery.task(bind=True)
def long_task(self):
    for i in range(1, 11):
        sleep(1)  # Sleep for a second
        current_task.update_state(state="PROGRESS", meta={"current": i, "total": 10})
    return {"current": 10, "total": 10, "status": "Task completed successfully"}


@celery.task(bind=True)
def convert_and_upload(self, uuid):
    self.update_state(
        state="PROGRESS",
        meta={"log": "Starting convert_and_upload", "uuid": uuid},
    )

    url = f"https://tensorflow-converter.s3.amazonaws.com/uploads/{uuid}.zip"
    # url = f"http://127.0.0.1:3001/static/uploads/{uuid}.zip"

    # Initialize S3 client
    session = boto3.Session(
        aws_access_key_id=os.getenv("AWS_S3_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_S3_SECRET_ACCESS_KEY"),
    )
    s3 = session.client("s3")
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME")

    tmp_dir = mkdtemp()
    tfjs_dir = os.path.join(tmp_dir, "tfjs")
    os.makedirs(tfjs_dir)

    try:
        self.update_state(state="PROGRESS", meta={"log": "Downloading generator"})
        r = requests.get(url)
        model_zip_path = os.path.join(tmp_dir, "model.zip")
        with open(model_zip_path, "wb") as f:
            f.write(r.content)

        self.update_state(state="PROGRESS", meta={"log": "Unzipping generator"})
        with zipfile.ZipFile(model_zip_path, "r") as zip_ref:
            zip_ref.extractall(tmp_dir)

        model_path = os.path.join(tmp_dir, "generator")

        self.update_state(state="PROGRESS", meta={"log": "Conversion started"})
        command = f"tensorflowjs_converter {model_path} {tfjs_dir}"
        process = subprocess.run(command, shell=True, capture_output=True, text=True)
        if process.returncode != 0:
            raise Exception(process.stderr)

        self.update_state(state="PROGRESS", meta={"log": "Conversion finished"})

        self.update_state(state="PROGRESS", meta={"log": "Zipping tfjs directory"})
        # Zip tfjs directory
        shutil.make_archive(tfjs_dir, "zip", tfjs_dir)

        # Upload to S3
        self.update_state(
            state="PROGRESS", meta={"log": "Uploading converted model to S3"}
        )
        zip_path = f"{tfjs_dir}.zip"
        s3_key = f"models/{uuid}.zip"
        s3.upload_file(zip_path, bucket_name, s3_key)
        uploaded_url = f"https://{bucket_name}.s3.amazonaws.com/{s3_key}"

        # Clean up
        self.update_state(state="PROGRESS", meta={"log": "Cleaning up"})
        shutil.rmtree(tmp_dir)

        return {"url": uploaded_url, "log": "Task completed successfully"}
    except Exception as e:
        shutil.rmtree(tmp_dir)
        raise e
