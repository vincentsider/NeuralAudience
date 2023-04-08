import os
import re
from langdetect import detect
from googletrans import Translator
from textblob import TextBlob
from flask import Flask, render_template, request
import requests
import openai
import emoji
from emoji.core import is_emoji as is_emoji_func
from google_trans_new import google_translator
from google.cloud import translate_v2 as translate
from google.oauth2 import service_account
import json
import re
from langdetect.lang_detect_exception import LangDetectException
from flask import jsonify
from flask_cors import CORS
from flask import Flask, send_file, Response

#credentials_content = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_CONTENT")
#credentials_info = json.loads(credentials_content)
#credentials = service_account.Credentials.from_service_account_info(credentials_info)
#translate_client = translate.Client(credentials=credentials)

# Load the JSON content from the Replit secret
service_account_info = json.loads(os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_CONTENT"))

# Create credentials from the service account info
credentials = service_account.Credentials.from_service_account_info(service_account_info)

# Create a Cloud Translation API client
translate_client = translate.Client(credentials=credentials)


# Create a Flask app instance
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://chat.openai.com"]}})
def get_video_title(video_id):
    url = f"https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet",
        "id": video_id,
        "key": os.environ.get("YOUTUBE_API_KEY")
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"An error occurred: {response.text}")
        return None

    data = response.json()

    if data["items"]:
        return data["items"][0]["snippet"]["title"]
    else:
        return None

api_key = os.environ.get("YOUTUBE_API_KEY")

translate_client = translate.Client(credentials=credentials)


emoji_sentiment_dict = {
    "😀": "positive",
    "😃": "positive",
    "😄": "positive",
    "😁": "positive",
    "😆": "positive",
    "😅": "positive",
    "😂": "positive",
    "🤣": "positive",
    "😊": "positive",
    "😇": "positive",
    "😠": "negative",
    "😡": "negative",
    "😢": "negative",
    "😥": "negative",
    "😓": "negative",
    "😩": "negative",
    "😖": "negative",
    "😞": "negative",
    "😟": "negative",
    "😔": "negative",
    "😕": "negative"
}

def extract_emojis_and_sentiment(text):
    emoji_sentiments = []
    for emoji, sentiment in emoji_sentiment_dict.items():
        if emoji in text:
            emoji_sentiments.append(sentiment)
    return emoji_sentiments

def is_emoji(text):
    return all(is_emoji_func(char) for char in text)


def translate_text(text):
    if not text or text.strip() == '' or is_emoji(text):
        return ''

    # Detect the source language of the text
    try:
        source_language = detect(text)
    except LangDetectException:
        return ''

    # If the source language is already English, return the original text
    if source_language == 'en':
        return text

    # Translate the text to English using the Cloud Translation API
    result = translate_client.translate(text, target_language='en')

    # Extract the translated text from the result
    translated_text = result['translatedText']

    return translated_text

def analyze_sentiment(text):
    analysis = TextBlob(text)
    if analysis.sentiment.polarity > 0.1:
        return "positive"
    elif analysis.sentiment.polarity < -0.1:
        return "negative"
    else:
        return "neutral"

def get_video_comments(video_id, max_results=100):
    url = f"https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "maxResults": max_results,
        "textFormat": "plainText",
        "key": os.environ.get("YOUTUBE_API_KEY")
    }

    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"An error occurred: {response.text}")
        return None

    data = response.json()

    comments = []
    nextPage_token = None
    while True:
        for item in data["items"]:
            comment = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            # Print the comment being processed
            print(f"Processing comment: '{comment}'")
          
            # Translate non-English comments
            translated_comment = translate_text(comment)
            print("Translated comment:", translated_comment)  # Print the translated comment
          
            # Extract emojis and calculate sentiment
            emoji_sentiments = extract_emojis_and_sentiment(translated_comment)

            # Analyze sentiment of the comment text
            text_sentiment = analyze_sentiment(translated_comment)

            # Combine emoji sentiment and text sentiment
            all_sentiments = emoji_sentiments + [text_sentiment]

            # Store the comment, translated comment, and sentiment analysis results
            comments.append({
                'original': comment,
                'translated': translated_comment,
                'sentiments': all_sentiments
            })

        nextPage_token = data.get('nextPageToken')
        if not nextPage_token:
            break
        params['pageToken'] = nextPage_token
        response = requests.get(url, params=params)
        data = response.json()

    return comments

@app.route('/.well-known/openapi.yaml')
def serve_openapi_yaml():
    with open('.well-known/openapi.yaml') as f:
        yaml_content = f.read()
    headers = {'Content-Disposition': 'inline'}
    return Response(yaml_content, mimetype='text/yaml', headers=headers)

@app.route('/.well-known/ai-plugin.json')
def serve_ai_plugin_json():
    with open('.well-known/ai-plugin.json') as f:
        json_content = f.read()
    headers = {'Content-Disposition': 'inline'}
    return Response(json_content, mimetype='application/json', headers=headers)

@app.route('/api/video_comments', methods=['POST'])
def api_video_comments():
    # Extract the video ID from the YouTube URL entered by the user
    video_id = extract_video_id(request.form['url'])

    if not video_id:
        return jsonify({"error": "Invalid YouTube URL"}), 400

    # Use the YouTube API to retrieve comments from the video
    comments = get_video_comments(video_id)

    # Return comments as JSON, including original, translated, and sentiments
    return jsonify(comments)

# New API endpoint for generating a persona based on comments
@app.route('/api/generate_persona', methods=['POST'])
def api_generate_persona():
    comments = request.get_json().get("comments", [])

    # Combine the translated comments into a single string
    comments_str = "\n".join([comment['translated'] for comment in comments])

    # Truncate comments to fit within the character limit
    max_chars = 2000
    comments_str_truncated = truncate_str(comments_str, max_chars)

    # Pass comments to GPT-3-5 API to generate persona
    prompt = f"Here are some comments from a YouTube video about {video_title}:\n{comments_str_truncated}\n\nBased on the above information, please answer the following questions:\n\n1. What is the general tone of the comments, and how does this reflect on the personality of the commenters?\n\n2. What are the key demographics of the commenters, such as age, gender, and location? How do these demographics relate to their personality traits?\n\n3. How do the commenters gather information and make decisions about purchases? What motivates them to engage with this content, and what are their goals and interests?\n\n4. How much do the commenters score on each of the Big Five personality traits (openness, conscientiousness, extraversion, agreeableness, and neuroticism)? Please rate their scores on a scale from 1 to 10, with 1 being low and 10 being high, and provide specific examples of comments that demonstrate these personality traits.\n\n5. What are the key demographics\n\n6. What are their main pain points\n\n7. What are their goals, motivations\n\n8.How do they gather information, make decisions about purchases?\n\n9. what are their Interests.\n\n10. What is the sentiment on a scale from 0 to 10, 0 being sad and 10 being happy"
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    completions = openai.Completion.create(
        engine="text-davinci-003",
        prompt=prompt,
        max_tokens=2000,
        n=1,
        stop=None,
        temperature=0.5,
        frequency_penalty=0,
        presence_penalty=0
    )

    # Extract the generated persona from the API response
    persona = completions.choices[0].text.strip()

    # Return the generated persona as the result of the form submission
    return jsonify({"persona": persona})

@app.route('/', methods=['GET', 'POST'])
def home():
    def truncate_str(s, max_chars):
        if len(s) > max_chars:
            return s[:max_chars] + "..."
        return s

    def extract_video_id(url):
        if "youtu.be" in url:
            return url.split('/')[-1]
        elif "youtube.com" in url:
            return url.split('v=')[1]
        else:
            return None

    persona = ""
    video_id = None  # Initialize video_id to None
    video_title = None  # Initialize video_id to None
    # If the form is submitted with a POST request
    if request.method == 'POST':
        # Extract the video ID from the YouTube URL entered by the user
        video_id = extract_video_id(request.form['url'])
        if video_id:
            # Use the YouTube API to retrieve comments from the video
            comments = get_video_comments(video_id)

            # Combine the translated comments into a single string
            comments_str = "\n".join([comment['translated'] for comment in comments])

            # Truncate comments to fit within the character limit
            max_chars = 2000
            comments_str_truncated = truncate_str(comments_str, max_chars)

    if video_id:  # Only call get_video_title if video_id is not None
        video_title = get_video_title(video_id)
    if video_title:   
        # Pass comments to GPT-3-5 API to generate persona
        prompt = f"Here are some comments from a YouTube video about {video_title}:\n{comments_str_truncated}\n\nBased on the above information, please answer the following questions:\n\n1. What is the general tone of the comments?\n\n2. What are the key demographics of the commenters?\n\n3. What are their goals and interests?\n\n4. Rate the commenters on each of the Big Five personality traits (openness, conscientiousness, extraversion, agreeableness, and neuroticism) on a scale from 1 to 10, with 1 being low and 10 being high. Provide examples of comments that demonstrate these traits.\n\n5. What are their main pain points?\n\n6. What intent do they show?\n\n7. What is the sentiment on a scale from 0 to 10, 0 being sad and 10 being happy\n\n8.Given the information acquired, name the persona"
        openai.api_key = os.environ.get("OPENAI_API_KEY")
        try:
            completions = openai.Completion.create(
                engine="text-davinci-003",
                prompt=prompt,
                max_tokens=2000,
                n=1,
                stop=None,
                temperature=0.8,
                frequency_penalty=0,
                presence_penalty=0
            )
            # Extract the generated persona from the API response
            persona = completions.choices[0].text.strip()

        except Exception as e:
            print(f"An error occurred while calling the OpenAI API: {e}")
            persona = "Error: Unable to generate persona."

      
        print("OpenAI completion:", completions)
    # Return the generated persona as the result of the form submission
        return persona
    else:
      if request.method == 'POST':
        return "Invalid YouTube URL"

    # If the form has not been submitted yet, or the video_title is None, display the homepage with the form
    if not video_id or not video_title:
        return render_template('/home.html', persona="")
    else:
        return render_template('/home.html', persona=persona)


#Start the Flask app and tell it to listen for incoming HTTP requests
#if __name__ == '__main__':
    #app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
