from flask import Blueprint, request, jsonify
from .tasks import optimize_task  # нашата Celery задача

# API blueprint for optimization endpoints
bp = Blueprint('optimize_api', __name__, url_prefix='/api/optimize')

@bp.route('', methods=['POST'])
def start_optimize():
    params = request.json
    job = optimize_task.apply_async(args=[params])
    return jsonify({"job_id": job.id}), 202

@bp.route('/status/<job_id>', methods=['GET'])
def get_status(job_id):
    job = optimize_task.AsyncResult(job_id)
    return jsonify({
        "status": job.status,
        "result": job.result if job.ready() else None
    })
