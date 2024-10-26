import re

def clean_subtitles(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split content into subtitle blocks
    blocks = re.split(r'\n\n+', content.strip())

    cleaned_blocks = []
    for i, block in enumerate(blocks, 1):
        lines = block.split('\n')
        if len(lines) >= 3:
            # Keep only the timestamp and subtitle text
            subtitle_text = ' '.join(lines[2:])
            
            # Remove the unwanted phrase
            subtitle_text = re.sub(r'^Here is the translation of the French subtitle text to English, maintaining the original formatting and line breaks:\s*', '', subtitle_text)
            subtitle_text = re.sub(r'^Here is the translation to English, maintaining the original formatting and line breaks:\s*', '', subtitle_text)
            subtitle_text = re.sub(r'^Here is the English translation with the original formatting and line breaks maintained:\s*', '', subtitle_text)
            subtitle_text = re.sub(r'^Here is the translation to English with the original formatting maintained:\s*', '', subtitle_text)

            
            # Remove any leading/trailing whitespace
            subtitle_text = subtitle_text.strip()
            
            cleaned_block = f"{i}\n{lines[1]}\n{subtitle_text}"
            cleaned_blocks.append(cleaned_block)

    # Join the cleaned blocks with double newlines
    cleaned_content = '\n\n'.join(cleaned_blocks)

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(cleaned_content)

    print(f"Cleaned subtitles saved to {output_file}")