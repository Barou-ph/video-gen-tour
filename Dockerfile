FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg fonts-open-sans && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

RUN mkdir -p output temp

RUN useradd -m -u 1000 user && chown -R user:user /app
USER user
ENV PATH="/home/user/.local/bin:$PATH"

EXPOSE 7860

CMD ["streamlit", "run", "app.py", "--server.port=7860", "--server.address=0.0.0.0", "--server.headless=true"]