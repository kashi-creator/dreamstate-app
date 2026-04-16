from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone
import json

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(100), default='Dreamer')
    subscription_status = db.Column(db.String(20), default='inactive')  # active, inactive, cancelled
    subscription_tier = db.Column(db.String(20), default='free')  # free, founder, premium
    stripe_customer_id = db.Column(db.String(255))
    stripe_subscription_id = db.Column(db.String(255))
    founder_code_used = db.Column(db.Boolean, default=False)
    onboarding_complete = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = db.Column(db.DateTime)

    dream_profile = db.relationship('DreamProfile', backref='user', uselist=False, cascade='all, delete-orphan')
    stories = db.relationship('StoryScript', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    audio_tracks = db.relationship('AudioTrack', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    play_sessions = db.relationship('PlaySession', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    streaks = db.relationship('ListeningStreak', backref='user', uselist=False, cascade='all, delete-orphan')
    questionnaire_responses = db.relationship('UserQuestionnaireResponse', backref='user', cascade='all, delete-orphan')
    notifications = db.relationship('Notification', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    settings = db.relationship('Settings', backref='user', uselist=False, cascade='all, delete-orphan')


class DreamProfile(db.Model):
    __tablename__ = 'dream_profiles'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    voice_rant_text = db.Column(db.Text)
    core_desire = db.Column(db.Text)
    identity_statement = db.Column(db.Text)
    emotional_tone = db.Column(db.Text)
    recurring_themes = db.Column(db.Text)
    shadow_blocks = db.Column(db.Text)
    dream_life_summary = db.Column(db.Text)
    raw_ai_analysis = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class StoryScript(db.Model):
    __tablename__ = 'story_scripts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), default='Untitled Story')
    story_type = db.Column(db.String(50))  # identity, wealth, love, health, spiritual, custom
    theme_id = db.Column(db.Integer, db.ForeignKey('themes.id'))
    frequency_id = db.Column(db.Integer, db.ForeignKey('frequencies.id'))
    voice_id = db.Column(db.String(100))
    voice_name = db.Column(db.String(100))
    script_text = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')  # draft, generating, ready, error
    generation_error = db.Column(db.Text)
    play_count = db.Column(db.Integer, default=0)
    total_listen_seconds = db.Column(db.Integer, default=0)
    is_favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    theme = db.relationship('Theme')
    frequency = db.relationship('Frequency')
    audio_tracks_rel = db.relationship('AudioTrack', backref='story', cascade='all, delete-orphan')


class AudioTrack(db.Model):
    __tablename__ = 'audio_tracks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    story_id = db.Column(db.Integer, db.ForeignKey('story_scripts.id'))
    file_path = db.Column(db.String(500))
    file_url = db.Column(db.String(500))
    duration_seconds = db.Column(db.Integer)
    file_size_bytes = db.Column(db.Integer)
    voice_id = db.Column(db.String(100))
    status = db.Column(db.String(20), default='pending')  # pending, processing, ready, error
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Theme(db.Model):
    __tablename__ = 'themes'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    color_primary = db.Column(db.String(7))
    color_secondary = db.Column(db.String(7))
    icon = db.Column(db.String(50))
    ambient_keywords = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


class Frequency(db.Model):
    __tablename__ = 'frequencies'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    hz_value = db.Column(db.String(20))
    brain_state = db.Column(db.String(50))
    best_for = db.Column(db.Text)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)


class PlaySession(db.Model):
    __tablename__ = 'play_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    story_id = db.Column(db.Integer, db.ForeignKey('story_scripts.id'))
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime)
    duration_seconds = db.Column(db.Integer, default=0)
    completed = db.Column(db.Boolean, default=False)


class ListeningStreak(db.Model):
    __tablename__ = 'listening_streaks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    current_streak = db.Column(db.Integer, default=0)
    longest_streak = db.Column(db.Integer, default=0)
    last_listen_date = db.Column(db.Date)
    total_sessions = db.Column(db.Integer, default=0)
    total_minutes = db.Column(db.Integer, default=0)


class UserQuestionnaireResponse(db.Model):
    __tablename__ = 'user_questionnaire_responses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_number = db.Column(db.Integer, nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    answer_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255))
    message = db.Column(db.Text)
    notification_type = db.Column(db.String(50), default='info')  # info, success, warning, story_ready
    is_read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class Settings(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    sleep_timer_default = db.Column(db.Integer, default=30)  # minutes
    autoplay_next = db.Column(db.Boolean, default=False)
    loop_story = db.Column(db.Boolean, default=True)
    preferred_voice = db.Column(db.String(100))
    notification_new_story = db.Column(db.Boolean, default=True)
    notification_streak = db.Column(db.Boolean, default=True)
    notification_tips = db.Column(db.Boolean, default=True)
    dark_mode = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


def seed_themes():
    """Seed the 8 themes if not already present."""
    themes_data = [
        {'slug': 'deep_forest', 'name': 'Deep Forest', 'description': 'Ancient woods where your deepest wisdom lives. Moss-covered paths lead to hidden clearings of power.', 'color_primary': '#1B4332', 'color_secondary': '#2D6A4F', 'icon': 'trees', 'ambient_keywords': 'rustling leaves, distant owl, creek bubbling, wind through pines', 'sort_order': 1},
        {'slug': 'ocean_depths', 'name': 'Ocean Depths', 'description': 'The infinite blue where consciousness dissolves into pure potential. Waves carry your intentions to every shore.', 'color_primary': '#023E8A', 'color_secondary': '#0077B6', 'icon': 'waves', 'ambient_keywords': 'ocean waves, whale song, underwater echoes, gentle current', 'sort_order': 2},
        {'slug': 'cosmic_void', 'name': 'Cosmic Void', 'description': 'Float among galaxies where reality is written. Stars whisper the code of manifestation.', 'color_primary': '#240046', 'color_secondary': '#7B2CBF', 'icon': 'stars', 'ambient_keywords': 'cosmic hum, stellar winds, nebula pulse, deep space silence', 'sort_order': 3},
        {'slug': 'miami_luxury', 'name': 'Miami Luxury', 'description': 'Sunset penthouses and ocean-view abundance. The frequency of wealth made tangible.', 'color_primary': '#FF6B6B', 'color_secondary': '#C9A84C', 'icon': 'building', 'ambient_keywords': 'distant bass, champagne fizz, ocean breeze, rooftop ambiance', 'sort_order': 4},
        {'slug': 'sacred_temple', 'name': 'Sacred Temple', 'description': 'Ancient sanctuary where divine intelligence flows through you. Incense and golden light.', 'color_primary': '#C9A84C', 'color_secondary': '#7B5EA7', 'icon': 'landmark', 'ambient_keywords': 'singing bowls, temple bells, sacred chant, flowing water', 'sort_order': 5},
        {'slug': 'golden_desert', 'name': 'Golden Desert', 'description': 'Endless golden sands where illusion burns away, leaving only truth and raw power.', 'color_primary': '#D4A574', 'color_secondary': '#C9A84C', 'icon': 'sun', 'ambient_keywords': 'desert wind, sand whisper, distant thunder, sunrise stillness', 'sort_order': 6},
        {'slug': 'rainforest_sovereign', 'name': 'Rainforest Sovereign', 'description': 'Lush, alive, untamed. You are the apex of this ecosystem, dripping with creative power.', 'color_primary': '#2D6A4F', 'color_secondary': '#40916C', 'icon': 'leaf', 'ambient_keywords': 'tropical rain, exotic birds, waterfall, jungle night', 'sort_order': 7},
        {'slug': 'penthouse_peak', 'name': 'Penthouse Peak', 'description': 'Glass and steel above the clouds. The view from the top of your empire.', 'color_primary': '#2B2D42', 'color_secondary': '#8D99AE', 'icon': 'gem', 'ambient_keywords': 'city hum, glass clink, distant skyline, elevator ding', 'sort_order': 8},
    ]
    for t in themes_data:
        existing = Theme.query.filter_by(slug=t['slug']).first()
        if not existing:
            db.session.add(Theme(**t))
    db.session.commit()


def seed_frequencies():
    """Seed the 8 frequencies if not already present."""
    freq_data = [
        {'slug': 'delta_sleep', 'name': 'Delta Sleep (0.5-4 Hz)', 'description': 'Deep dreamless sleep. Your subconscious is wide open for reprogramming.', 'hz_value': '2', 'brain_state': 'Deep Sleep', 'best_for': 'Sleep stories, deep subconscious reprogramming', 'sort_order': 1},
        {'slug': 'theta_hypnagogic', 'name': 'Theta Hypnagogic (4-8 Hz)', 'description': 'The doorway between sleep and waking. Maximum suggestibility and vivid imagery.', 'hz_value': '6', 'brain_state': 'Hypnagogic', 'best_for': 'Visualization, creative manifestation, meditation', 'sort_order': 2},
        {'slug': 'alpha_relaxed', 'name': 'Alpha Relaxed (8-13 Hz)', 'description': 'Calm, present awareness. Perfect for affirmations that feel natural and true.', 'hz_value': '10', 'brain_state': 'Relaxed Focus', 'best_for': 'Daytime listening, affirmations, gentle reprogramming', 'sort_order': 3},
        {'slug': 'gamma_peak', 'name': 'Gamma Peak (30-100 Hz)', 'description': 'Heightened perception and insight. Your brain at its most powerful.', 'hz_value': '40', 'brain_state': 'Peak Performance', 'best_for': 'Focus, motivation, breakthrough insights', 'sort_order': 4},
        {'slug': '432hz_harmony', 'name': '432 Hz Universal Harmony', 'description': 'The frequency of the universe. Natural, healing, mathematically perfect.', 'hz_value': '432', 'brain_state': 'Harmony', 'best_for': 'General wellbeing, alignment, daily listening', 'sort_order': 5},
        {'slug': '528hz_love', 'name': '528 Hz Love Frequency', 'description': 'The miracle tone. DNA repair, transformation, and unconditional love.', 'hz_value': '528', 'brain_state': 'Love & Healing', 'best_for': 'Self-love, healing, relationship manifestation', 'sort_order': 6},
        {'slug': 'solfeggio_852', 'name': '852 Hz Spiritual Awakening', 'description': 'Return to spiritual order. Awakens intuition and connects to higher self.', 'hz_value': '852', 'brain_state': 'Spiritual Awakening', 'best_for': 'Spiritual growth, intuition, higher consciousness', 'sort_order': 7},
        {'slug': 'no_frequency', 'name': 'No Frequency (Voice Only)', 'description': 'Pure voice without binaural beats. Clean and direct.', 'hz_value': '0', 'brain_state': 'Natural', 'best_for': 'Anytime listening, background play', 'sort_order': 8},
    ]
    for f in freq_data:
        existing = Frequency.query.filter_by(slug=f['slug']).first()
        if not existing:
            db.session.add(Frequency(**f))
    db.session.commit()
