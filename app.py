from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
import os
from flask_sqlalchemy import SQLAlchemy
import datetime
import base64
import operator

import tensorflow as tf
from dotenv import load_dotenv

from imageai.Detection import ObjectDetection
from keras import backend as K

import cv2

load_dotenv()
tf.config.set_visible_devices([], 'GPU')

# os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'
# gpus = tf.config.experimental.list_physical_devices('GPU')
# if gpus:
#     try:
#         # Currently, memory growth needs to be the same across GPUs
#         for gpu in gpus:
#             tf.config.experimental.set_memory_growth(gpu, True)
#         logical_gpus = tf.config.experimental.list_logical_devices('GPU')
#         print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
#     except RuntimeError as e:
#         # Memory growth must be set before GPUs have been initialized
#         print(e)

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
    # Serialized from "latitude:xx,longitude:yy"
    map_data = db.Column(db.String, nullable=True)
    sensors = db.relationship('Sensor', backref=db.backref(
        'gallery', lazy='joined'), lazy=True)

    def __repr__(self):
        return '<Gallery %r>' % self.filename

    def get_filename(self):
        return self.filename


class Sensor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gallery_id = db.Column(db.Integer, db.ForeignKey(
        'gallery.id'), nullable=False)
    type = db.Column(db.String, nullable=False)
    data = db.Column(db.String, nullable=False)

    def __repr__(self):
        return self.data


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/home')
def home():
    photos = Gallery.query.all()
    return jsonify([{'id': photo.id, 'description': photo.description, 'filename': photo.filename,
                     'img_url': photo.img_url, 'created_at': photo.created_at, 'map_data': photo.map_data} for
                    photo in photos])


@app.route("/sensor/<int:gallery_id>")
def get_sensor(gallery_id):
    gallery = Gallery.query.filter_by(id=gallery_id).first()
    sensor = gallery.sensors[0]

    if sensor is not None:
        return jsonify({"id": sensor.id, "type": sensor.type, "gallery_id": sensor.gallery_id, "data": sensor.data})


@app.route("/delete/<int:gallery_id>", methods=['DELETE'])
def delete_item(gallery_id):
    # TODO: DELETE FILE
    item = Gallery.query.filter_by(id=gallery_id).first()
    sensor = Sensor.query.filter_by(gallery_id=gallery_id).first()
    try:
        # os.remove(item.img_url)
        db.session.delete(sensor)
        db.session.delete(item)
        db.session.commit()
        return jsonify({'success': True})
    except:
        print("Delete {} failed".format(item.filename))
    return jsonify({'success': False})


def rotate(fpath):
    image = cv2.imread(fpath)
    rotated = cv2.rotate(image, cv2.cv2.ROTATE_90_CLOCKWISE)
    cv2.imwrite(fpath, rotated)


def predict(fpath):
    K.clear_session()
    yolo_obj = ObjectDetection()
    yolo_obj.setModelTypeAsYOLOv3()
    exec_path = os.getcwd()
    yolo_obj.setModelPath(os.path.join(exec_path, "yolo.h5"))
    yolo_obj.loadModel()
    detections = yolo_obj.detectObjectsFromImage(
        input_image=fpath, output_image_path=fpath)
    results = []
    for objects in detections:
        result = objects["name"] + " : " + \
                 str(int(objects["percentage_probability"]))
        results.append(result)
        print(objects["name"], " : ", objects["percentage_probability"])
    K.clear_session()
    list_result = '. '.join(map(str, results))
    return list_result


@app.route('/upload', methods=['POST'])
def upload_image():
    print(request.form['filename'])

    if request.method == 'POST':
        sensor_data = str(request.form['sensor'])
        filename = secure_filename(request.form['filename'])
        fpath = os.path.join('files/photos/', filename)
        map_data = str(request.form['mapData'])
        # fpath_dummy = os.path.join('files/photos_dummy/', filename)
        file = base64.b64decode(request.form['raw'])
        with open(fpath, 'wb') as fout:
            fout.write(file)

        rotate(fpath)
        list_result = predict(fpath)

        photo = Gallery(filename=filename, description=list_result,
                        img_url=fpath, created_at=datetime.datetime.now(), map_data=map_data)
        db.session.add(photo)
        db.session.commit()
        sensor = Sensor(gallery_id=photo.id,
                        type='accelerometer', data=sensor_data)
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
    # app.run("192.168.8.101", debug=True)
