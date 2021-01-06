from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
from flask_sqlalchemy import SQLAlchemy
import datetime
import base64

import tensorflow as tf
from tensorflow.keras.applications.resnet50 import preprocess_input, decode_predictions
from tensorflow.keras.preprocessing import image
import numpy as np
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'files/photos/'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///main.db'
ALLOWED_EXTENSIONS = {'png', 'jpeg', 'jpg'}
db = SQLAlchemy(app)


class Gallery(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, nullable=False)
    description = db.Column(db.String, nullable=True)
    img_url = db.Column(db.String, nullable=False)
    created_at = db.Column(db.DATETIME, nullable=True)
    map_data = db.Column(db.String, nullable=True)  # Serialized from "latitude:xx,longitude:yy"
    sensors = db.relationship('Sensor', backref=db.backref('gallery', lazy='joined'), lazy=True)

    def __repr__(self):
        return '<Gallery %r>' % self.filename

    def get_filename(self):
        return self.filename


class Sensor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gallery_id = db.Column(db.Integer, db.ForeignKey('gallery.id'), nullable=False)
    type = db.Column(db.String, nullable=False)
    data = db.Column(db.String, nullable=False)

    def __repr__(self):
        return self.id


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/home')
def home():
    photos = Gallery.query.all()
    model = tf.keras.applications.resnet50.ResNet50()
    for photo in photos:
        img_path = os.path.join('files/photos/', photo.filename)
        img = image.load_img(img_path, target_size=(224, 224))
        img_array = image.img_to_array(img)
        img_batch = np.expand_dims(img_array, axis=0)
        img_preprocessed = preprocess_input(img_batch)
        prediction = model.predict(img_preprocessed)
        result = decode_predictions(prediction, top=1)[0][0][1].replace("_", " ")
        accuracy = decode_predictions(prediction, top=1)[0][0][2]
        photo.description = result + " (" + str(accuracy) + "%)"

    # print(jsonify(
    #     [{'id': photo.id, 'filename': photo.filename, 'img_url': photo.img_url, 'created_at': photo.created_at} for
    #      photo in photos]))
    return jsonify([{'id': photo.id, 'description': photo.description, 'filename': photo.filename,
                     'img_url': photo.img_url, 'created_at': photo.created_at, 'map_data': photo.map_data} for
                    photo in photos])


@app.route("/sensor/<int:gallery_id>")
def get_sensor(gallery_id):
    gallery = Gallery.query.filter_by(id=gallery_id).first()
    sensor = gallery.sensors[0]

    if sensor is not None:
        return jsonify({"id": sensor.id, "type": sensor.type, "gallery_id": sensor.gallery_id, "data": sensor.data})


@app.route('/upload', methods=['POST'])
def upload_image():
    print(request.form['filename'])

    if request.method == 'POST':
        sensor_data = str(request.form['sensor'])
        filename = secure_filename(request.form['filename'])
        fpath = os.path.join('files/photos/', filename)
        file = base64.b64decode(request.form['raw'])
        with open(fpath, 'wb') as fout:
            fout.write(file)

        photo = Gallery(filename=filename, description="Test",
                        img_url=fpath, created_at=datetime.datetime.now())
        db.session.add(photo)
        db.session.commit()
        sensor = Sensor(gallery_id=photo.id, type='accelerometer', data=sensor_data)
        db.session.add(sensor)
        db.session.commit()
        # f.save(fpath)
        return jsonify({
            'id': photo.id,
            'filename': photo.filename,
            'description': photo.description,
            'img_url': photo.img_url,
            'created_at': photo.created_at
        })
    return {'success': False}


@app.route('/files/photos/<path:filename>', methods=['GET'])
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'],
                               filename, as_attachment=True)


if __name__ == '__main__':
    app.run(host=os.getenv('HOSTNAME'), debug=True)
