import os
import json
import threading
from datetime import datetime, timezone, date, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, jsonify, abort, session)
from flask_login import (LoginManager, login_user, logout_user,
                         login_required, current_user)
import bcrypt
import bleach

from models import (db, User, DreamProfile, StoryScript, AudioTrack,
                    Theme, Frequency, PlaySession, ListeningStreak,
                    UserQuestionnaireResponse, Notification, Settings,
                    seed_themes, seed_frequencies)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dreamstate-dev-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///dreamstate.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix postgres:// -> postgresql:// for SQLAlchemy 1.4+
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# ---------------------------------------------------------------------------
# Config / API keys
# ---------------------------------------------------------------------------
FOUNDER_CODE = os.environ.get('FOUNDER_CODE', 'DREAMSTATE2026')
STRIPE_SECRET = os.environ.get('STRIPE_SECRET_KEY', 'REPLACE')
STRIPE_PUBLISHABLE = os.environ.get('STRIPE_PUBLISHABLE_KEY', 'REPLACE')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', 'REPLACE')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY', 'REPLACE')
ELEVENLABS_KEY = os.environ.get('ELEVENLABS_API_KEY', 'REPLACE')
OPENAI_KEY = os.environ.get('OPENAI_API_KEY', 'REPLACE')


def api_configured(key):
    return key and 'REPLACE' not in key and len(key) > 10


# ---------------------------------------------------------------------------
# Questionnaire questions
# ---------------------------------------------------------------------------
QUESTIONNAIRE = [
    "What does your dream life look like when you wake up in the morning?",
    "Where are you living? Describe the space, the light, the feeling.",
    "What work are you doing, and how does it feel in your body?",
    "How much money flows into your life, and what does abundance mean to you?",
    "Who is beside you? Describe your ideal relationships.",
    "What does your body look and feel like at your highest vibration?",
    "What did you believe about yourself as a child that still echoes today?",
    "What limiting belief are you most ready to release?",
    "When you feel truly powerful, what does that feel like?",
    "What emotion do you avoid feeling the most?",
    "If fear had no grip on you, what would you do tomorrow?",
    "What is the version of you that already has everything you desire like?",
    "What spiritual or inner practice grounds you?",
    "What does freedom mean to you at the deepest level?",
    "What recurring dream or vision keeps showing up in your life?",
    "What legacy do you want to leave behind?",
    "What does your inner voice say when you are completely still?",
    "Write a single sentence that describes the person you are becoming.",
]

STORY_TYPES = [
    {'id': 'identity', 'name': 'Identity Shift', 'description': 'Become the version of you who already has it all', 'icon': 'fingerprint'},
    {'id': 'wealth', 'name': 'Wealth Activation', 'description': 'Reprogram your relationship with money and abundance', 'icon': 'gem'},
    {'id': 'love', 'name': 'Love & Relationships', 'description': 'Attract and embody the love you deserve', 'icon': 'heart'},
    {'id': 'health', 'name': 'Health & Vitality', 'description': 'Your body as a temple of radiant energy', 'icon': 'sparkles'},
    {'id': 'spiritual', 'name': 'Spiritual Awakening', 'description': 'Connect to the infinite intelligence within you', 'icon': 'eye'},
    {'id': 'custom', 'name': 'Custom Dream', 'description': 'Tell us exactly what you want to manifest', 'icon': 'wand-magic-sparkles'},
]


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


# ---------------------------------------------------------------------------
# Login manager
# ---------------------------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def subscription_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('login'))
        if current_user.subscription_status != 'active':
            flash('You need an active subscription to access this.', 'warning')
            return redirect(url_for('pricing'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Context processors
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    unread = 0
    if current_user.is_authenticated:
        unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return dict(unread_count=unread, now=datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# ROUTES: Landing / Auth
# ---------------------------------------------------------------------------
@app.route('/')
def welcome():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('welcome.html')


@app.route('/pricing')
def pricing():
    return render_template('pricing.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = bleach.clean(request.form.get('email', '').strip().lower())
        password = request.form.get('password', '')
        display_name = bleach.clean(request.form.get('display_name', 'Dreamer').strip())
        founder_code = request.form.get('founder_code', '').strip()

        if not email or not password:
            flash('Email and password are required.', 'error')
            return redirect(url_for('signup'))
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return redirect(url_for('signup'))
        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return redirect(url_for('signup'))

        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user = User(
            email=email,
            password_hash=pw_hash,
            display_name=display_name or 'Dreamer',
            subscription_status='active',
            subscription_tier='founder' if founder_code == FOUNDER_CODE else 'premium',
            founder_code_used=(founder_code == FOUNDER_CODE),
        )
        db.session.add(user)
        db.session.commit()

        # Create default settings & streak
        db.session.add(Settings(user_id=user.id))
        db.session.add(ListeningStreak(user_id=user.id))
        db.session.add(Notification(
            user_id=user.id,
            title='Welcome to DREAMSTATE',
            message='Your reality is about to shift. Complete onboarding to build your dream profile.',
            notification_type='success',
            link='/onboarding'
        ))
        db.session.commit()

        login_user(user)
        return redirect(url_for('onboarding'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()

        if user and bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
            if user.subscription_status != 'active':
                flash('Your subscription is not active. Please subscribe to continue.', 'warning')
                return redirect(url_for('pricing'))
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            login_user(user)
            next_page = request.args.get('next')
            if not user.onboarding_complete:
                return redirect(url_for('onboarding'))
            return redirect(next_page or url_for('dashboard'))
        flash('Invalid email or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been signed out.', 'info')
    return redirect(url_for('welcome'))


@app.route('/validate-founder-code', methods=['POST'])
def validate_founder_code():
    data = request.get_json() or {}
    code = data.get('code', '').strip()
    return jsonify({'success': code == FOUNDER_CODE})


# ---------------------------------------------------------------------------
# ROUTES: Onboarding
# ---------------------------------------------------------------------------
@app.route('/onboarding')
@login_required
def onboarding():
    return render_template('onboarding.html', questions=QUESTIONNAIRE)


@app.route('/api/onboarding/voice-rant', methods=['POST'])
@login_required
def save_voice_rant():
    data = request.get_json() or {}
    text = bleach.clean(data.get('text', ''))
    if not text:
        return jsonify({'success': False, 'error': 'No text provided'})

    profile = DreamProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = DreamProfile(user_id=current_user.id)
        db.session.add(profile)
    profile.voice_rant_text = text
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/onboarding/questionnaire', methods=['POST'])
@login_required
def save_questionnaire():
    data = request.get_json() or {}
    question_num = data.get('question_number')
    answer = bleach.clean(data.get('answer', ''))

    if question_num is None or question_num < 1 or question_num > len(QUESTIONNAIRE):
        return jsonify({'success': False, 'error': 'Invalid question number'})

    existing = UserQuestionnaireResponse.query.filter_by(
        user_id=current_user.id, question_number=question_num
    ).first()

    if existing:
        existing.answer_text = answer
    else:
        resp = UserQuestionnaireResponse(
            user_id=current_user.id,
            question_number=question_num,
            question_text=QUESTIONNAIRE[question_num - 1],
            answer_text=answer,
        )
        db.session.add(resp)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/onboarding/process-profile', methods=['POST'])
@login_required
def process_profile():
    profile = DreamProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        profile = DreamProfile(user_id=current_user.id)
        db.session.add(profile)

    responses = UserQuestionnaireResponse.query.filter_by(user_id=current_user.id).order_by(
        UserQuestionnaireResponse.question_number
    ).all()

    answers_text = "\n".join([f"Q{r.question_number}: {r.question_text}\nA: {r.answer_text}" for r in responses if r.answer_text])
    rant = profile.voice_rant_text or ''
    combined = f"Voice rant:\n{rant}\n\nQuestionnaire:\n{answers_text}"

    if api_configured(ANTHROPIC_KEY):
        # Process with Claude in background
        def process_with_ai():
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                resp = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=2000,
                    messages=[{
                        "role": "user",
                        "content": f"""Analyze this person's dream profile. Extract:
1. Core Desire (1-2 sentences)
2. Identity Statement (a powerful "I am" statement for them)
3. Emotional Tone (the dominant emotional frequency they want)
4. Recurring Themes (3-5 themes as comma-separated list)
5. Shadow Blocks (limiting beliefs or fears holding them back, 2-3)
6. Dream Life Summary (a vivid 3-4 sentence description of their ideal life)

Their responses:
{combined}

Return as JSON with keys: core_desire, identity_statement, emotional_tone, recurring_themes, shadow_blocks, dream_life_summary"""
                    }]
                )
                text = resp.content[0].text
                # Try to parse JSON from response
                try:
                    start = text.find('{')
                    end = text.rfind('}') + 1
                    if start >= 0 and end > start:
                        parsed = json.loads(text[start:end])
                    else:
                        parsed = {}
                except json.JSONDecodeError:
                    parsed = {}

                with app.app_context():
                    p = DreamProfile.query.filter_by(user_id=current_user.id).first()
                    if p:
                        p.core_desire = parsed.get('core_desire', '')
                        p.identity_statement = parsed.get('identity_statement', '')
                        p.emotional_tone = parsed.get('emotional_tone', '')
                        p.recurring_themes = parsed.get('recurring_themes', '')
                        p.shadow_blocks = parsed.get('shadow_blocks', '')
                        p.dream_life_summary = parsed.get('dream_life_summary', '')
                        p.raw_ai_analysis = text
                        db.session.commit()
            except Exception as e:
                print(f"AI processing error: {e}")
                with app.app_context():
                    _placeholder_profile(current_user.id, combined)

        thread = threading.Thread(target=process_with_ai)
        thread.start()
        thread.join(timeout=30)
    else:
        _placeholder_profile(current_user.id, combined)

    current_user.onboarding_complete = True
    db.session.commit()
    return jsonify({'success': True})


def _placeholder_profile(user_id, combined_text):
    profile = DreamProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = DreamProfile(user_id=user_id)
        db.session.add(profile)
    profile.core_desire = "To live authentically in alignment with my highest vision."
    profile.identity_statement = "I am the creator of my reality, and I live in my dream state now."
    profile.emotional_tone = "Empowered, peaceful, abundant"
    profile.recurring_themes = "Freedom, abundance, authentic self-expression, love, purpose"
    profile.shadow_blocks = "Fear of not being enough, resistance to receiving, attachment to old identity"
    profile.dream_life_summary = "A life of radiant abundance where every morning feels like a gift. Deep purpose flows through meaningful work, surrounded by love and beauty."
    profile.raw_ai_analysis = "Placeholder - configure ANTHROPIC_API_KEY for AI analysis"
    db.session.commit()


# ---------------------------------------------------------------------------
# ROUTES: Dashboard
# ---------------------------------------------------------------------------
@app.route('/dashboard')
@login_required
@subscription_required
def dashboard():
    if not current_user.onboarding_complete:
        return redirect(url_for('onboarding'))

    stories = StoryScript.query.filter_by(user_id=current_user.id).order_by(
        StoryScript.updated_at.desc()
    ).limit(5).all()

    active_story = StoryScript.query.filter_by(
        user_id=current_user.id, status='ready'
    ).order_by(StoryScript.updated_at.desc()).first()

    streak = ListeningStreak.query.filter_by(user_id=current_user.id).first()
    total_stories = StoryScript.query.filter_by(user_id=current_user.id).count()
    total_minutes = streak.total_minutes if streak else 0

    return render_template('dashboard.html',
                           stories=stories,
                           active_story=active_story,
                           streak=streak,
                           total_stories=total_stories,
                           total_minutes=total_minutes)


# ---------------------------------------------------------------------------
# ROUTES: Story Creation
# ---------------------------------------------------------------------------
@app.route('/create-story')
@login_required
@subscription_required
def create_story():
    themes = Theme.query.filter_by(is_active=True).order_by(Theme.sort_order).all()
    frequencies = Frequency.query.filter_by(is_active=True).order_by(Frequency.sort_order).all()
    profile = DreamProfile.query.filter_by(user_id=current_user.id).first()

    voices = _get_voices()

    return render_template('create_story.html',
                           story_types=STORY_TYPES,
                           themes=themes,
                           frequencies=frequencies,
                           voices=voices,
                           profile=profile)


def _get_voices():
    if api_configured(ELEVENLABS_KEY):
        try:
            import requests as req
            resp = req.get('https://api.elevenlabs.io/v1/voices',
                           headers={'xi-api-key': ELEVENLABS_KEY}, timeout=10)
            if resp.status_code == 200:
                return [{'id': v['voice_id'], 'name': v['name']} for v in resp.json().get('voices', [])]
        except Exception:
            pass
    # Placeholder voices
    return [
        {'id': 'serene_female', 'name': 'Serene (Female)'},
        {'id': 'deep_male', 'name': 'Deep Calm (Male)'},
        {'id': 'ethereal_female', 'name': 'Ethereal (Female)'},
        {'id': 'warm_male', 'name': 'Warm Guide (Male)'},
        {'id': 'whisper_female', 'name': 'Whisper (Female)'},
    ]


@app.route('/api/create-story', methods=['POST'])
@login_required
@subscription_required
def api_create_story():
    data = request.get_json() or {}
    story_type = data.get('story_type', 'identity')
    theme_id = data.get('theme_id')
    frequency_id = data.get('frequency_id')
    voice_id = data.get('voice_id', 'serene_female')
    voice_name = data.get('voice_name', 'Serene')
    custom_prompt = bleach.clean(data.get('custom_prompt', ''))

    story = StoryScript(
        user_id=current_user.id,
        story_type=story_type,
        theme_id=theme_id,
        frequency_id=frequency_id,
        voice_id=voice_id,
        voice_name=voice_name,
        status='generating',
        title=f"{story_type.replace('_', ' ').title()} Story",
    )
    db.session.add(story)
    db.session.commit()

    story_id = story.id
    user_id = current_user.id

    def generate_script():
        with app.app_context():
            s = db.session.get(StoryScript, story_id)
            profile = DreamProfile.query.filter_by(user_id=user_id).first()
            theme = db.session.get(Theme, theme_id) if theme_id else None
            freq = db.session.get(Frequency, frequency_id) if frequency_id else None

            profile_context = ""
            if profile:
                profile_context = f"""
Dream Profile:
- Core Desire: {profile.core_desire or 'N/A'}
- Identity: {profile.identity_statement or 'N/A'}
- Emotional Tone: {profile.emotional_tone or 'N/A'}
- Themes: {profile.recurring_themes or 'N/A'}
- Dream Life: {profile.dream_life_summary or 'N/A'}
"""

            theme_context = f"\nTheme: {theme.name} - {theme.description}\nAmbient: {theme.ambient_keywords}" if theme else ""
            freq_context = f"\nFrequency: {freq.name} - {freq.best_for}" if freq else ""
            custom_context = f"\nCustom Request: {custom_prompt}" if custom_prompt else ""

            prompt = f"""Write a powerful subliminal/manifestation script for a {story_type} story.
{profile_context}{theme_context}{freq_context}{custom_context}

Guidelines:
- Write in second person ("you")
- 800-1200 words
- Begin with a relaxation induction (3-4 sentences)
- Weave in the person's specific desires and identity
- Use present tense affirmations embedded in narrative
- Include sensory details (sight, sound, touch, smell)
- Build to an emotional crescendo
- End with an anchoring statement
- Make it deeply personal based on their profile
- Tone: hypnotic, intimate, powerful

Return ONLY the script text, no headers or meta-commentary."""

            if api_configured(ANTHROPIC_KEY):
                try:
                    import anthropic
                    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
                    resp = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=3000,
                        messages=[{"role": "user", "content": prompt}]
                    )
                    s.script_text = resp.content[0].text
                    s.status = 'ready'
                    s.title = _generate_title(story_type, theme)
                except Exception as e:
                    s.status = 'error'
                    s.generation_error = str(e)
            else:
                s.script_text = _placeholder_script(story_type, profile)
                s.status = 'ready'
                s.title = _generate_title(story_type, theme)

            db.session.commit()

            # Create notification
            n = Notification(
                user_id=user_id,
                title='Story Ready' if s.status == 'ready' else 'Story Error',
                message=f'Your story "{s.title}" is ready to play.' if s.status == 'ready' else f'Error generating story: {s.generation_error}',
                notification_type='story_ready' if s.status == 'ready' else 'warning',
                link=f'/scripts/{s.id}/read'
            )
            db.session.add(n)
            db.session.commit()

    thread = threading.Thread(target=generate_script)
    thread.start()

    return jsonify({'success': True, 'story_id': story_id, 'message': 'Story is being generated...'})


def _generate_title(story_type, theme):
    type_titles = {
        'identity': 'The One Who Already Is',
        'wealth': 'Rivers of Gold',
        'love': 'The Frequency of Love',
        'health': 'Temple of Light',
        'spiritual': 'The Infinite Within',
        'custom': 'My Dream Manifested',
    }
    base = type_titles.get(story_type, 'Dream Story')
    if theme:
        return f"{base} - {theme.name}"
    return base


def _placeholder_script(story_type, profile):
    name = "Dreamer"
    desire = "your highest vision"
    if profile:
        desire = profile.core_desire or desire

    return f"""Close your eyes. Take a deep, slow breath in... and release.

Feel your body softening. Every muscle, every tension, dissolving like morning mist over still water. You are safe here. You are held. You are exactly where you need to be.

Now, see yourself stepping through a doorway of golden light. On the other side is the life you have always known was yours. Not a fantasy - your reality. The one you are stepping into right now.

You are the person who has {desire}. This is not something you are reaching for. It is something you already are. Feel it in your bones. Feel the certainty of it settling into every cell of your being.

Your morning begins with peace. You open your eyes and the first thing you feel is gratitude - not as an exercise, but as a natural overflow. The space around you reflects who you truly are. Beautiful. Intentional. Yours.

You move through your day with quiet power. People feel it when you enter a room - not because you demand attention, but because your energy is magnetic. You have done the inner work. You have released what no longer serves you. And now, the universe mirrors your alignment.

Money flows to you easily and naturally. Not because you chase it, but because you are in perfect resonance with abundance. Opportunities arrive as if orchestrated by an intelligence far greater than the logical mind. And they are.

Your relationships are deep, authentic, and nourishing. You attract people who see you - truly see you - and who rise to meet your frequency. Love is not something you search for. It is something you radiate.

Your body is strong, vital, alive with energy. Every breath fills you with light. You honor this vessel, and it honors you back with health, beauty, and resilience.

This is not a distant dream. This is your now. This is your DREAMSTATE made real.

Take one more deep breath. Feel this reality anchoring into your subconscious mind. Every time you listen to this, the neural pathways of your new identity strengthen. You are being reprogrammed for the life you deserve.

You already live there. Now... let your body rest as your mind continues to build this new world.

You are becoming. You are arrived. You are home."""


# ---------------------------------------------------------------------------
# ROUTES: Library
# ---------------------------------------------------------------------------
@app.route('/library')
@login_required
@subscription_required
def library():
    stories = StoryScript.query.filter_by(user_id=current_user.id).order_by(
        StoryScript.is_favorite.desc(), StoryScript.updated_at.desc()
    ).all()
    return render_template('library.html', stories=stories)


@app.route('/api/stories/<int:story_id>/delete', methods=['POST'])
@login_required
def delete_story(story_id):
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()
    db.session.delete(story)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/stories/<int:story_id>/duplicate', methods=['POST'])
@login_required
def duplicate_story(story_id):
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()
    new_story = StoryScript(
        user_id=current_user.id,
        title=f"{story.title} (Copy)",
        story_type=story.story_type,
        theme_id=story.theme_id,
        frequency_id=story.frequency_id,
        voice_id=story.voice_id,
        voice_name=story.voice_name,
        script_text=story.script_text,
        status='ready' if story.script_text else 'draft',
    )
    db.session.add(new_story)
    db.session.commit()
    return jsonify({'success': True, 'story_id': new_story.id})


@app.route('/api/stories/<int:story_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(story_id):
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()
    story.is_favorite = not story.is_favorite
    db.session.commit()
    return jsonify({'success': True, 'is_favorite': story.is_favorite})


# ---------------------------------------------------------------------------
# ROUTES: Script Editor
# ---------------------------------------------------------------------------
@app.route('/scripts/<int:story_id>/edit', methods=['GET', 'POST'])
@login_required
@subscription_required
def edit_script(story_id):
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        story.script_text = request.form.get('script_text', '')
        story.title = bleach.clean(request.form.get('title', story.title))
        story.status = 'ready'
        db.session.commit()
        flash('Script saved.', 'success')
        return redirect(url_for('edit_script', story_id=story_id))
    return render_template('edit_script.html', story=story)


@app.route('/scripts/<int:story_id>/read')
@login_required
@subscription_required
def read_script(story_id):
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()
    return render_template('read_script.html', story=story)


@app.route('/api/stories/<int:story_id>/status')
@login_required
def story_status(story_id):
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()
    return jsonify({
        'success': True,
        'status': story.status,
        'title': story.title,
        'error': story.generation_error
    })


# ---------------------------------------------------------------------------
# ROUTES: Play Sessions / Streaks
# ---------------------------------------------------------------------------
@app.route('/api/play/start', methods=['POST'])
@login_required
def start_play():
    data = request.get_json() or {}
    story_id = data.get('story_id')
    story = StoryScript.query.filter_by(id=story_id, user_id=current_user.id).first_or_404()

    session_obj = PlaySession(user_id=current_user.id, story_id=story_id)
    db.session.add(session_obj)
    story.play_count += 1
    db.session.commit()
    return jsonify({'success': True, 'session_id': session_obj.id})


@app.route('/api/play/end', methods=['POST'])
@login_required
def end_play():
    data = request.get_json() or {}
    session_id = data.get('session_id')
    duration = data.get('duration_seconds', 0)

    play_session = PlaySession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if play_session:
        play_session.ended_at = datetime.now(timezone.utc)
        play_session.duration_seconds = duration
        play_session.completed = duration > 60

        # Update streak
        streak = ListeningStreak.query.filter_by(user_id=current_user.id).first()
        if not streak:
            streak = ListeningStreak(user_id=current_user.id)
            db.session.add(streak)

        today = date.today()
        if streak.last_listen_date == today - timedelta(days=1):
            streak.current_streak += 1
        elif streak.last_listen_date != today:
            streak.current_streak = 1
        streak.last_listen_date = today
        streak.longest_streak = max(streak.longest_streak, streak.current_streak)
        streak.total_sessions += 1
        streak.total_minutes += duration // 60

        # Update story stats
        story = db.session.get(StoryScript, play_session.story_id)
        if story:
            story.total_listen_seconds += duration

        db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# ROUTES: Dream Profile
# ---------------------------------------------------------------------------
@app.route('/dream-profile')
@login_required
@subscription_required
def dream_profile():
    profile = DreamProfile.query.filter_by(user_id=current_user.id).first()
    responses = UserQuestionnaireResponse.query.filter_by(
        user_id=current_user.id
    ).order_by(UserQuestionnaireResponse.question_number).all()
    return render_template('dream_profile.html', profile=profile, responses=responses)


@app.route('/api/dream-profile/update', methods=['POST'])
@login_required
def update_dream_profile():
    data = request.get_json() or {}
    profile = DreamProfile.query.filter_by(user_id=current_user.id).first()
    if not profile:
        return jsonify({'success': False, 'error': 'No profile found'})

    for field in ['core_desire', 'identity_statement', 'emotional_tone',
                  'recurring_themes', 'shadow_blocks', 'dream_life_summary']:
        if field in data:
            setattr(profile, field, bleach.clean(data[field]))

    db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# ROUTES: Settings
# ---------------------------------------------------------------------------
@app.route('/settings', methods=['GET', 'POST'])
@login_required
@subscription_required
def settings():
    user_settings = Settings.query.filter_by(user_id=current_user.id).first()
    if not user_settings:
        user_settings = Settings(user_id=current_user.id)
        db.session.add(user_settings)
        db.session.commit()

    if request.method == 'POST':
        # Account
        name = bleach.clean(request.form.get('display_name', '').strip())
        if name:
            current_user.display_name = name

        # Listening prefs
        user_settings.sleep_timer_default = int(request.form.get('sleep_timer', 30))
        user_settings.loop_story = 'loop_story' in request.form
        user_settings.autoplay_next = 'autoplay_next' in request.form

        # Notifications
        user_settings.notification_new_story = 'notification_new_story' in request.form
        user_settings.notification_streak = 'notification_streak' in request.form
        user_settings.notification_tips = 'notification_tips' in request.form

        db.session.commit()
        flash('Settings saved.', 'success')
        return redirect(url_for('settings'))

    return render_template('settings.html', user_settings=user_settings)


@app.route('/api/settings/change-password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json() or {}
    current_pw = data.get('current_password', '')
    new_pw = data.get('new_password', '')

    if not bcrypt.checkpw(current_pw.encode('utf-8'), current_user.password_hash.encode('utf-8')):
        return jsonify({'success': False, 'error': 'Current password is incorrect'})
    if len(new_pw) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters'})

    current_user.password_hash = bcrypt.hashpw(new_pw.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# ROUTES: Notifications
# ---------------------------------------------------------------------------
@app.route('/notifications')
@login_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()
    ).limit(50).all()
    return render_template('notifications.html', notifications=notifs)


@app.route('/api/notifications/read', methods=['POST'])
@login_required
def mark_notifications_read():
    data = request.get_json() or {}
    notif_id = data.get('notification_id')
    if notif_id:
        n = Notification.query.filter_by(id=notif_id, user_id=current_user.id).first()
        if n:
            n.is_read = True
    else:
        Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# ROUTES: Admin
# ---------------------------------------------------------------------------
@app.route('/admin')
@login_required
@admin_required
def admin():
    users = User.query.order_by(User.created_at.desc()).all()
    total_users = User.query.count()
    total_stories = StoryScript.query.count()
    total_sessions = PlaySession.query.count()
    themes = Theme.query.order_by(Theme.sort_order).all()
    frequencies = Frequency.query.order_by(Frequency.sort_order).all()
    return render_template('admin.html',
                           users=users,
                           total_users=total_users,
                           total_stories=total_stories,
                           total_sessions=total_sessions,
                           themes=themes,
                           frequencies=frequencies)


@app.route('/api/admin/toggle-admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin():
    data = request.get_json() or {}
    user = db.session.get(User, data.get('user_id'))
    if user and user.id != current_user.id:
        user.is_admin = not user.is_admin
        db.session.commit()
    return jsonify({'success': True})


@app.route('/api/admin/toggle-user-status', methods=['POST'])
@login_required
@admin_required
def toggle_user_status():
    data = request.get_json() or {}
    user = db.session.get(User, data.get('user_id'))
    if user and user.id != current_user.id:
        user.subscription_status = 'inactive' if user.subscription_status == 'active' else 'active'
        db.session.commit()
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500


@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


# ---------------------------------------------------------------------------
# DB init
# ---------------------------------------------------------------------------
with app.app_context():
    db.create_all()
    seed_themes()
    seed_frequencies()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
