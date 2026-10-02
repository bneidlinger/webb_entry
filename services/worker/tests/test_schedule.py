from redis import Redis
from rq.job import Job

from worker.schedule import MAST_POLL_JOB_ID, S3_LISTING_JOB_ID


def test_periodic_ids_are_accepted_by_installed_rq():
    # Creating (but not saving) a Job validates IDs without contacting Redis.
    for job_id in (MAST_POLL_JOB_ID, S3_LISTING_JOB_ID):
        job = Job.create("worker.jobs.mast_poll.run", id=job_id, connection=Redis())
        assert job.id == job_id
