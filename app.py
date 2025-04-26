
from flask import (Flask, request, session, redirect, url_for,
                   render_template_string, send_file)
from gtts import gTTS
from langdetect import detect
from io import BytesIO
from deep_translator import GoogleTranslator

app = Flask(__name__)
app.secret_key = 'replace-with-your-secret-key'

# Parse custom prompts, supporting single or range-based entries
def parse_prompts(raw_lines):
    entries = []
    auto_idx = 0
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        if ':' in line and '-' in line.split(':',1)[0]:
            rng, txt = line.split(':',1)
            s, e = map(int, rng.split('-',1))
            entries.append({'start': s-1, 'end': e-1, 'text': txt.strip()})
        else:
            entries.append({'start': auto_idx, 'end': auto_idx, 'text': line})
            auto_idx += 1
    return entries

# Fetch sentence-by-sentence literal translations via deep-translator
def fetch_translations(sentences, target='en'):
    prompts = []
    translator = GoogleTranslator(source='auto', target=target)
    for s in sentences:
        try:
            prompts.append(translator.translate(s))
        except Exception:
            prompts.append('')
    return prompts

# Inline HTML templates (all in English)
INDEX_HTML = '''<!doctype html>
<html>
<head><meta charset="utf-8"><title>Memorization Aid - Input</title></head>
<body>
  <h1>Stage A: Input</h1>
  <form method="post">
    <label>Text to memorize (one sentence per line):<br>
      <textarea name="text" rows="8" cols="60"></textarea>
    </label><br><br>
    <label>Custom prompts (one per line or start-end: prompt):<br>
      <textarea name="prompts" rows="8" cols="60"></textarea>
    </label><br><br>
    <label>Translation language:
      <select name="target_lang">
        <option value="en">English</option>
        <option value="zh-cn">Chinese</option>
        <option value="fr">French</option>
        <option value="es">Spanish</option>
      </select>
    </label><br><br>
    <label><input type="checkbox" name="use_group" checked> Use custom prompts</label><br>
    <label><input type="checkbox" name="use_auto"> Use translation prompts</label><br>
    <label><input type="checkbox" name="use_tts" checked> Use TTS audio</label><br><br>
    <button type="submit">Start Memorization</button>
  </form>
</body>
</html>'''

MEMORIZE_HTML = '''<!doctype html>
<html>
<head><meta charset="utf-8"><title>Memorization Aid - Practice</title></head>
<body>
  <h1>Stage B: Practice (Sentence {{ idx+1 }} / {{ total }})</h1>

  {% if prompt_text %}
  <p><strong>Prompt:</strong> {{ prompt_text }}</p>
  {% endif %}

  {% if use_tts %}
  <p><strong>Listen:</strong></p>
  <audio controls>
    <source src="{{ url_for('tts') }}?text={{ sentence|urlencode }}" type="audio/mpeg">
    Your browser does not support audio.
  </audio>
  {% endif %}

  <form method="post">
    <textarea name="user_input" rows="4" cols="60"
      placeholder="Type what you recall here"></textarea><br><br>
    <button type="submit">Submit</button>
  </form>
</body>
</html>'''

RESULT_HTML = '''<!doctype html>
<html>
<head><meta charset="utf-8"><title>Memorization Aid - Results</title></head>
<body>
  <h1>Stage C: Results</h1>
  <table border="1" cellpadding="6">
    <tr><th>Original</th><th>Your Input</th><th>Status</th></tr>
    {% for idx, res in results.items() %}
    <tr>
      <td>{{ sentences[idx] }}</td>
      <td>{{ res.input }}</td>
      <td>{{ res.status }}</td>
    </tr>
    {% endfor %}
  </table>
  <br>
  <a href="{{ url_for('index') }}">Restart</a>
</body>
</html>'''

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        sentences = [s.strip() for s in request.form['text'].splitlines() if s.strip()]
        session['sentences'] = sentences
        session['group_prompts'] = parse_prompts(request.form['prompts'].splitlines())
        session['use_group'] = 'use_group' in request.form
        session['use_auto'] = 'use_auto' in request.form
        session['use_tts'] = 'use_tts' in request.form
        session['target_lang'] = request.form.get('target_lang', 'en')
        if session['use_auto']:
            session['auto_prompts'] = fetch_translations(sentences, session['target_lang'])
        else:
            session['auto_prompts'] = [''] * len(sentences)
        session['results'] = {}
        return redirect(url_for('memorize', idx=0))
    return render_template_string(INDEX_HTML)

@app.route('/tts')
def tts():
    text = request.args.get('text', '')
    try:
        lang = detect(text)
    except:
        lang = 'en'
    mp3_fp = BytesIO()
    gTTS(text=text, lang=lang).write_to_fp(mp3_fp)
    mp3_fp.seek(0)
    return send_file(mp3_fp, mimetype='audio/mpeg')

@app.route('/memorize', methods=['GET', 'POST'])
def memorize():
    sentences = session.get('sentences', [])
    group_prompts = session.get('group_prompts', [])
    auto_prompts = session.get('auto_prompts', [])
    use_group = session.get('use_group', False)
    use_auto = session.get('use_auto', False)
    use_tts = session.get('use_tts', False)
    idx = int(request.args.get('idx', 0))

    if request.method == 'POST':
        user_input = request.form['user_input'].strip()
        orig = sentences[idx]
        orig_words = orig.split()
        input_words = user_input.split()
        errors = sum(1 for o, u in zip(orig_words, input_words) if o != u)
        errors += abs(len(orig_words) - len(input_words))
        rate = errors / len(orig_words) if orig_words else 1
        if rate == 0:
            status = 'Perfect'
        elif rate <= 0.5:
            status = 'Partial'
        else:
            status = 'None'
        session['results'][idx] = {'input': user_input, 'status': status}
        next_idx = idx + 1
        if next_idx < len(sentences):
            return redirect(url_for('memorize', idx=next_idx))
        return redirect(url_for('result'))

    # Determine prompt text based on user choices
    prompt_text = ''
    if use_group:
        for ent in group_prompts:
            if ent['start'] <= idx <= ent['end']:
                prompt_text = ent['text']
                break
    if not prompt_text and use_auto:
        prompt_text = auto_prompts[idx]

    return render_template_string(
        MEMORIZE_HTML,
        idx=idx,
        total=len(sentences),
        sentence=sentences[idx],
        prompt_text=prompt_text,
        use_tts=use_tts
    )

@app.route('/result')
def result():
    return render_template_string(
        RESULT_HTML,
        sentences=session.get('sentences', []),
        results=session.get('results', {})
    )

if __name__ == '__main__':
    app.run(debug=True)
