import os
import functools
from moviepy.editor import VideoFileClip
from fastapi import FastAPI, UploadFile, Depends, HTTPException, Response
from .models import Video, get_db

class VideoAPI:
    def __init__(self, db=Depends(get_db)):
        self.db = db

    @staticmethod
    def is_video_blocked(video_id: int, db):
        '''
        This function checks if a video is blocked or not
        '''
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="No Video Found For Provided Id!!")
        return video.is_blocked

    @staticmethod
    def cache_and_block(func):
        @functools.wraps(func)
        @functools.lru_cache(maxsize=128)
        def wrapper(video_id: int, db=Depends(get_db)):
            if VideoAPI.is_video_blocked(video_id, db):
                print(f"Video {video_id} is blocked.")
                raise HTTPException(status_code=403, detail="Video download is blocked.")
            return func(video_id, db)
        return wrapper

    async def upload_video(self, video: UploadFile):
        '''
        This endpoint is used to upload video and convert it to mp4
        '''
        original_filename = video.filename

        os.makedirs("videos", exist_ok=True)

        with open(f"{original_filename}", "wb") as file:
            contents = await video.read()
            file.write(contents)

        # Convert the video to .mp4
        clip = VideoFileClip(f"{original_filename}")
        new_video_filename = f"{original_filename.split('.')[0]}.mp4"
        clip.write_videofile(f"videos/{new_video_filename}")

        # Saving video to database
        new_video = Video(original_filename=original_filename, name=new_video_filename, size=video.size)
        self.db.add(new_video)
        self.db.commit()

        os.remove(original_filename)

        return {"message": "Video uploaded and converted successfully!!"}

    def search_videos(self, name: str = None, size: int = None):
        '''
        This endpoint is used to search videos by name or size
        '''
        query = self.db.query(Video)

        if name:
            query = query.filter(Video.name.ilike(f"%{name}%"))

        if size:
            query = query.filter(Video.size == size)

        videos = query.all()

        if not videos:
            raise HTTPException(status_code=404, detail="No Such Videos Found!!")

        return videos

    @cache_and_block
    def download_video(self, video_id: int):
        '''
        This endpoint is used to download uploaded videos
        '''
        video = self.db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="No Video Found For Provided Id!!")

        video_path = f"videos/{video.name}"

        if not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Video File Not Available!")

        with open(video_path, "rb") as video_file:
            video_data = video_file.read()

        response = Response(content=video_data, media_type="video/mp4")
        response.headers["Content-Disposition"] = f"attachment; filename={video.original_filename}"

        return response


app = FastAPI()
video_api = VideoAPI()

@app.post("/upload")
async def upload_video(video: UploadFile, db=Depends(get_db)):
    return await video_api.upload_video(video)

@app.get("/search")
def search_videos(name: str = None, size: int = None, db=Depends(get_db)):
    return video_api.search_videos(name, size)

@app.get("/download/{video_id}")
def download_video(video_id: int, db=Depends(get_db)):
    return video_api.download_video(video_id)
