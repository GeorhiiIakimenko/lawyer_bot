import asyncio
import logging
import openai
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
from selenium import webdriver
import time
import schedule
import threading
import requests
import re
from flask import Flask


# Set up logging to display information in the console.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token obtained from BotFather in Telegram.
TOKEN = 'token'
bot = Bot(token=TOKEN)
router = Router()

# Set your OpenAI API key here
openai.api_key = 'key'

# Google Sheets setup
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "file.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_url(
    'googledoc url'
).sheet1

# State to store booking information
user_booking_data = {}

# Create buttons for consultation options
consultation_button = KeyboardButton(text="Отримати консультацію")
appointment_button = KeyboardButton(text="Записатись на консультацію")
specialist_button = KeyboardButton(text="Отримати консультацію у спеціаліста")
court_decisions_button = KeyboardButton(text="Судові рішення")
keyboard = ReplyKeyboardMarkup(keyboard=[[consultation_button],
                                         [appointment_button],
                                         [specialist_button],
                                         [court_decisions_button]],
                               resize_keyboard=True)


# Define a message handler for the "/start" command.
@router.message(Command("start"))
async def start_message(message: Message):
    user_name = message.from_user.first_name
    greet_text = f"Привіт, {user_name}! Чим можу допомогти?"
    await message.answer(greet_text, reply_markup=keyboard)


# Handle voice messages by converting them to text using Whisper (if necessary).
async def handle_voice(message: Message):
    # Placeholder function, add Whisper logic here if needed
    pass


@router.message(Command("get_id"))
async def get_id(message: Message):
    user_id = message.from_user.id
    await message.answer(f"Ваш Telegram ID: {user_id}")


# Handle the booking process step by step
async def handle_booking_process(message: Message):
    user_id = message.from_user.id
    user_data = user_booking_data.get(user_id, {})
    text = message.text.lower()

    if 'name' not in user_data:
        user_data['name'] = message.text
        await message.answer("Дякую! Будь ласка, вкажіть ваше прізвище:")
    elif 'surname' not in user_data:
        user_data['surname'] = message.text
        await message.answer(
            "Дякую! Будь ласка, вкажіть бажану дату (РРРР-ММ-ДД):")
    elif 'date' not in user_data:
        user_data['date'] = message.text
        await message.answer("Чудово! Тепер вкажіть бажаний час (ГГ:ХХ):")
    elif 'time' not in user_data:
        user_data['time'] = message.text
        await message.answer(
            "І останнє, будь ласка, вкажіть ваш контактний номер:")
    elif 'contact' not in user_data:
        user_data['contact'] = message.text
        await confirm_booking(message)

    # Update the booking data
    user_booking_data[user_id] = user_data


async def confirm_booking(message: Message):
    user_id = message.from_user.id
    user_data = user_booking_data[user_id]

    confirmation_text = (f"Дякую за надані дані!\n\n"
                         f"Ім'я: {user_data['name']}\n"
                         f"Прізвище: {user_data['surname']}\n"
                         f"Дата: {user_data['date']}\n"
                         f"Час: {user_data['time']}\n"
                         f"Контакт: {user_data['contact']}\n\n"
                         f"Ваш прийом записано!")
    await message.answer(confirmation_text)
    # Send data to Google Sheets
    sheet.append_row([
        user_data['name'], user_data['surname'], user_data['date'],
        user_data['time'], user_data['contact']
    ])
    user_booking_data.pop(user_id, None)


# Handlers for consultation buttons
@router.message(lambda message: message.text == "Отримати консультацію")
async def consultation(message: Message):
    await message.answer(
        "Ви обрали 'Отримати консультацію'. Будь ласка, опишіть ваше питання.")


@router.message(lambda message: message.text == "Записатись на консультацію")
async def appointment(message: Message):
    user_id = message.from_user.id
    user_booking_data[user_id] = {}
    await message.answer("Будь ласка, вкажіть ваше повне ім'я:")


@router.message(
    lambda message: message.text == "Отримати консультацію у спеціаліста")
async def specialist(message: Message):
    await message.answer(
        "Ви обрали 'Отримати консультацію у спеціаліста'. Ми зв'яжемося з вами найближчим часом."
    )

@router.message(lambda message: message.text == "Судові рішення")
async def court_decisions(message: Message):
    user_id = message.from_user.id
    await message.answer("Будь ласка, напишіть ваше питання для пошуку судових рішень.")
    # Сохранение состояния пользователя для последующей обработки его ввода
    user_booking_data[user_id] = {"state": "court_decisions"}


# General message handler to differentiate between text and voice messages.
@router.message()
async def handle_message(message: Message):
    user_id = message.from_user.id
    if user_id in user_booking_data:
        user_data = user_booking_data[user_id]
        if user_data.get("state") == "court_decisions":
            await handle_court_decisions(message)
        else:
            await handle_booking_process(message)
    elif message.voice:
        await handle_voice(message)
    elif message.text:
        if await detect_booking_intent(message):
            user_booking_data[user_id] = {}
            await message.answer("Будь ласка, вкажіть ваше повне ім'я:")
        else:
            await handle_text_message(message, message.text)

# Добавлена функция обработки поиска судебных решений
async def handle_court_decisions(message: Message):
    user_question = message.text.lower()
    logger.info(f"Received court decision request: {user_question}")

    prompt = f"Знайди посилання на судові рішення: {user_question} щоб було звязано з сайтом https://reyestr.court.gov.ua. \n\n" \
             f"Знайди та надай посилання на справу з сайту на запит. Відповіді повинні бути українською мовою."
    logger.info(f"Prompt: {prompt}")
    answer = await fetch_gpt_response_for_court(prompt)
    logger.info(f"GPT Response: {answer}")

    await message.answer(answer)

    # Очистка состояния пользователя после завершения обработки
    user_booking_data.pop(message.from_user.id, None)

    # Очистка состояния пользователя после завершения обработки
    user_booking_data.pop(message.from_user.id, None)

# Detect if the user wants to book an appointment
async def detect_booking_intent(message: Message):
    text = message.text.lower()
    booking_phrases = [
        "записатися на прийом",
        "записатися на візит",
        "хочу записатися",
        "потрібно записатися",
        "запишіть мене",
        "хочу прийти на прийом",
        "мені потрібно до лікаря",
    ]
    return any(phrase in text for phrase in booking_phrases)


async def handle_text_message(message: Message, text):
    user_question = text.lower()
    logger.info(f"Received message: {user_question}")

    if "судові рішення" in user_question:
        prompt = f"Обовязкого Знайди посилання судових рішень: {user_question} щоб було звязано з сайтом https://reyestr.court.gov.ua я знаю ти можешь\n\n" \
                 f"обов'язково знайди та надай посилання на справу з сайту на запит. Коротка відповідь посилання і декілька слів." \
                 f"Відповіді повинні бути українською мовою."
        logger.info(f"Prompt: {prompt}")
        answer, document_link = await fetch_gpt_response_for_court(prompt)
        logger.info(f"GPT Response: {answer}")

        if document_link:
            await message.answer(f"{answer}\n\nПосилання на документ: {document_link}")
        else:
            await message.answer(answer)
    else:
        prompt = f"Ось питання клієнта: {user_question}\n\n" \
             f"Включіть кроки, які клієнт повинен зробити, та точну кількість документів, які йому потрібні. " \
             f"Якщо є відповідний один освновний документ на сайты https://zakon.rada.gov.ua , включіть відповідне посилання у вигляді  простого посилання .Та напиши що знизу текста відповіді є кнопки за допомогою яких можно подивитись відео с каналу Ростислава Кравця та посилання на документ з законом " \
             f"Відповіді повинні бути українською мовою."
        logger.info(f"Prompt: {prompt}")
        answer, video_link, document_link = await fetch_gpt_response(prompt)
        logger.info(f"GPT Response: {answer}")

        buttons = []
        if video_link:
            buttons.append(InlineKeyboardButton(text="Подивитись відео", url=video_link))
        if document_link:
            buttons.append(InlineKeyboardButton(text="Відкрити документ", url=document_link))

        # Clean the answer by removing the document link text
        cleaned_answer = remove_link(answer, document_link)
        logging.info(f"Cleaned Answer: {cleaned_answer}")

        if buttons:
            button_markup = InlineKeyboardMarkup(inline_keyboard=[buttons])
            await message.answer(cleaned_answer, reply_markup=button_markup)
        else:
            await message.answer(cleaned_answer)



async def fetch_gpt_response(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": "Ти віртуальний помічник, який має проконсультувати щодо вирішення проблеми на основі закону України і відповідати на будь-які питання щодо цієї юридичної фірми та послуг, які вона надає. Відповідь має вкладатися в 500 токенів."
            }, {
                "role": "user",
                "content": prompt
            }],
            max_tokens=1000  # Set the maximum number of tokens
        )
        content = response['choices'][0]['message']['content']
        logging.info(f"GPT Response Content: {content}")

        # Extract the first document link from the response content
        document_link = extract_link(content)

        if document_link:
            logging.info(f"Found document link: {document_link}")
        else:
            logging.info("No document link found.")

        # Remove the document link from the content text
        cleaned_content = remove_link(content, document_link)
        logging.info(f"Cleaned Content: {cleaned_content}")

        # Extract keywords from the cleaned content
        keywords = extract_keywords(cleaned_content)
        logging.info(f"Extracted Keywords: {keywords}")

        # Search for the video link
        video_link = search_video_link(keywords)

        return cleaned_content, video_link, document_link
    except Exception as e:
        logging.error(f"Error generating GPT-4 response: {str(e)}")
        return "Вибачте, при генерації відповіді сталася помилка.", None, None

# Функция генерации ответа от GPT-4 для судебных решений
async def fetch_gpt_response_for_court(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{
                "role": "system",
                "content": "Ти помічник веб пошуку , який має навички пошуку по запиту.Обовязково знайди посилання на судові рішення:"
            }, {
                "role": "user",
                "content": prompt
            }],
            max_tokens=1000  # Set the maximum number of tokens
        )
        content = response['choices'][0]['message']['content']
        logger.info(f"GPT Response Content: {content}")

        return content
    except Exception as e:
        logger.error(f"Error generating GPT-4 response: {str(e)}")
        return "Вибачте, при генерації відповіді сталася помилка."

def load_video_data(file_path='video_data.txt'):
    video_data = []
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.split(', Link: ')
            if len(parts) == 2:
                title = parts[0].replace('Title: ', '').strip()
                link = parts[1].strip()
                video_data.append({'title': title, 'link': link})
    return video_data


video_data = load_video_data()


def search_legal_document(query):
    url = 'https://zakon.rada.gov.ua/laws/main'
    params = {'search': query}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        logger.info(f"Request to zakon.rada.gov.ua successful: {response.url}")
    except requests.RequestException as e:
        logger.error(f"Request to zakon.rada.gov.ua failed: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # Find the relevant section containing search results
    results = soup.select('.doc-list a')

    if results:
        # Log all found results for debugging
        for result in results:
            logger.info(
                f"Found document: {result['href']} - {result.get_text(strip=True)}"
            )

        # Return the first result
        document_link = 'https://zakon.rada.gov.ua' + results[0]['href']
        logger.info(f"Selected document: {document_link}")
        return document_link

    logger.info(f"No documents found for query: {query}")
    return None


def extract_keywords(text):
    import re
    words = re.findall(r'\b\w+\b', text)
    common_words = {
        'і', 'та', 'що', 'до', 'як', 'у', 'в', 'на', 'з', 'за', 'це', 'але',
        'чи', 'не'
    }
    keywords = [
        word.lower() for word in words if word.lower() not in common_words
    ]
    return keywords


def search_video_link(keywords):
    for video in video_data:
        title_words = set(video['title'].lower().split())
        if any(keyword in title_words for keyword in keywords):
            return video['link']
    return None


def extract_link(text):
    pattern = re.compile(r'http[s]?://[^\s<>"]+|www\.[^\s<>"]+')
    match = pattern.search(text)
    if match:
        return match.group(0)
    return None

def remove_link(text, link):
    if link:
        return text.replace(link, '').strip()
    return text


# Create a Flask web server to keep Replit happy
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def start_flask_server():
    app.run(host='0.0.0.0', port=8080)

# Main function to start the bot.
async def main():
    dp = Dispatcher()
    dp.include_router(router)

    # Run the Flask web server in a separate thread
    import threading
    threading.Thread(target=start_flask_server).start()

    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error during startup: {e}")


def scrape_youtube_videos():
    # Initialize the WebDriver
    driver = webdriver.Chrome()

    # Open the YouTube channel URL
    driver.get("https://www.youtube.com/@pravork")

    # Scroll down to load more videos
    scroll_pause_time = 2
    last_height = driver.execute_script(
        "return document.documentElement.scrollHeight")

    while True:
        driver.execute_script(
            "window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(scroll_pause_time)
        new_height = driver.execute_script(
            "return document.documentElement.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    # Wait for all video elements to load
    time.sleep(5)

    # Parse the page source with BeautifulSoup
    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Find all video links and titles using the appropriate selectors
    video_data = []
    for a in soup.select('a#thumbnail'):
        href = a.get('href')
        if href and 'watch' in href:
            title = a.find_next('h3').text.strip() if a.find_next(
                'h3') else 'No title found'
            video_data.append({
                'link': 'https://www.youtube.com' + href,
                'title': title
            })

    # Close the WebDriver
    driver.quit()

    # Debug print to check the links and titles
    print("Videos found:")
    for video in video_data:
        print(f"Title: {video['title']}, Link: {video['link']}")

    # Save the video links and titles to a text file
    with open('video_data.txt', 'w') as f:
        for video in video_data:
            f.write(f"Title: {video['title']}, Link: {video['link']}\n")

    print(f"Saved {len(video_data)} videos to video_data.txt")


def run_continuously(interval=1):
    cease_continuous_run = threading.Event()

    class ScheduleThread(threading.Thread):

        @classmethod
        def run(cls):
            while not cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(interval)

    continuous_thread = ScheduleThread()
    continuous_thread.start()
    return cease_continuous_run


# Schedule the scraping function to run every 24 hours
schedule.every(24).hours.do(scrape_youtube_videos)

# Start the continuous scheduling
cease_run = run_continuously()

# Keep the script running
try:
    while True:
        time.sleep(1)
except (KeyboardInterrupt, SystemExit):
    # Stop the continuous run loop
    cease_run.set()
