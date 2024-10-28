import os
import re
import anthropic
import discord
import logging
from typing import List, Dict
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import time
import asyncio
from aiohttp import ClientError
load_dotenv()
# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Environment variables
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", 0))

# Initialize clients
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Supported languages
SUPPORTED_LANGUAGES = {
    "english": "en",
    "french": "fr",
    "spanish": "es",
    "german": "de",
    "italian": "it",
    "portuguese": "pt",
    "russian": "ru",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
    "arabic": "ar"
}

class SRTTranslatorBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()
        
    async def on_ready(self):
        logger.info(f'{self.user} has connected to Discord!')
        channel = self.get_channel(CHANNEL_ID)
        if channel:
            logger.info(f'Bot is configured for channel: {channel.name}')
        else:
            logger.error(f'Could not find channel with ID: {CHANNEL_ID}')

bot = SRTTranslatorBot()

def read_srt_file(file_path: str) -> str:
    logger.info(f"Reading SRT file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        logger.info(f"Successfully read SRT file: {file_path}")
        return content
    except Exception as e:
        logger.error(f"Error reading SRT file {file_path}: {str(e)}")
        raise

def write_srt_file(file_path: str, content: str):
    logger.info(f"Writing translated SRT file: {file_path}")
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        logger.info(f"Successfully wrote translated SRT file: {file_path}")
    except Exception as e:
        logger.error(f"Error writing SRT file {file_path}: {str(e)}")
        raise

async def translate_batch(texts: List[str], target_lang: str, max_retries: int = 3) -> List[str]:
    logger.info(f"Translating batch of {len(texts)} text blocks to {target_lang}")
    
    for attempt in range(max_retries):
        try:
            # Add rate limiting delay
            await asyncio.sleep(1.2)
            
            prompt = f"Translate the following subtitle texts to {target_lang}. Maintain the original formatting and line breaks. Separate each translation with '---'.\n\n"
            prompt += "\n---\n".join(texts)
            
            # Run the synchronous Anthropic client in a thread pool
            message = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=8000,
                    system="You are a professional translator.",
                    messages=[
                        {"role": "user", "content": prompt}
                    ]
                )
            )
            
            logger.info("Successfully received translation response")
            translations = message.content[0].text.split('---')
            return [t.strip() for t in translations]
            
        except Exception as e:
            logger.error(f"Error on attempt {attempt + 1}/{max_retries}: {str(e)}")
            if attempt == max_retries - 1:  # Last attempt
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
            continue

async def translate_srt_content(content: str, target_lang: str) -> str:
    logger.info(f"Starting translation to {target_lang}")
    try:
        # Split the SRT content into blocks
        srt_blocks = re.split(r'\n\n', content.strip())
        logger.info(f"Found {len(srt_blocks)} subtitle blocks to translate")
        
        translated_blocks = []
        batch_size = 200
        
        for i in range(0, len(srt_blocks), batch_size):
            batch = srt_blocks[i:i+batch_size]
            texts_to_translate = []
            
            for block in batch:
                lines = block.split('\n')
                if len(lines) >= 3:
                    subtitle_text = '\n'.join(lines[2:])
                    texts_to_translate.append(subtitle_text)
                else:
                    texts_to_translate.append('')
            
            try:
                # Add await here
                translated_texts = await translate_batch(texts_to_translate, target_lang)
                
                for j, translated_text in enumerate(translated_texts):
                    block = batch[j]
                    lines = block.split('\n')
                    if len(lines) >= 3:
                        translated_block = f"{lines[0]}\n{lines[1]}\n{translated_text}"
                        translated_blocks.append(translated_block)
                    else:
                        logger.warning(f"Skipping block {i+j+1} due to insufficient lines")
            
            except Exception as e:
                logger.error(f"Error translating batch {i//batch_size + 1}: {str(e)}")
                raise
        
        return '\n\n'.join(translated_blocks)
    except Exception as e:
        logger.error(f"Error during translation process: {str(e)}")
        raise

@bot.tree.command(name="translate", description="Translate an SRT file to the specified language")
async def translate(interaction: discord.Interaction):
    # Check if command is used in the correct channel
    if interaction.channel_id != CHANNEL_ID:
        await interaction.response.send_message(
            f"This command can only be used in <#{CHANNEL_ID}>",
            ephemeral=True
        )
        return

    await interaction.response.send_message("Please upload an SRT file to translate.")

    def check(m):
        return (
            m.author == interaction.user and 
            m.channel.id == CHANNEL_ID and 
            len(m.attachments) > 0
        )

    try:
        file_message = await bot.wait_for('message', timeout=120.0, check=check)
        attachment = file_message.attachments[0]
        
        if not attachment.filename.endswith('.srt'):
            await interaction.followup.send("Please upload a valid SRT file.")
            return

        # Download the file
        temp_input_path = f"temp_input_{interaction.user.id}.srt"
        await attachment.save(temp_input_path)

        # Ask for target language
        await interaction.followup.send("Please specify the target language (e.g., french, spanish, german, etc.)")
        
        def lang_check(m):
            return (
                m.author == interaction.user and 
                m.channel.id == CHANNEL_ID
            )
        
        lang_message = await bot.wait_for('message', timeout=30.0, check=lang_check)
        target_lang = lang_message.content.lower()
        
        if target_lang not in SUPPORTED_LANGUAGES:
            await interaction.followup.send(f"Unsupported language. Supported languages are: {', '.join(SUPPORTED_LANGUAGES.keys())}")
            return

        # Read the input file
        srt_content = read_srt_file(temp_input_path)
        
        # Translate the content
        await interaction.followup.send("Translation in progress... Please wait.")
        translated_content = await translate_srt_content(srt_content, target_lang)
        
        # Save translated content
        temp_output_path = f"temp_output_{interaction.user.id}.srt"
        write_srt_file(temp_output_path, translated_content)
        
        # Send the translated file
        await interaction.followup.send(
            f"Here's your translated SRT file in {target_lang}:",
            file=discord.File(temp_output_path)
        )
        
        # Clean up temporary files
        os.remove(temp_input_path)
        os.remove(temp_output_path)
        
    except TimeoutError:
        await interaction.followup.send("Timed out. Please try again.")
    except Exception as e:
        logger.error(f"Error in translate command: {str(e)}")
        await interaction.followup.send("An error occurred during translation. Please try again.")

def main():
    if not CHANNEL_ID:
        logger.error("DISCORD_CHANNEL_ID environment variable is not set!")
        return
        
    try:
        logger.info(f"Starting Discord bot (Channel ID: {CHANNEL_ID})")
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}")

if __name__ == "__main__":
    main()