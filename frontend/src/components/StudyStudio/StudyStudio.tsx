import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  BookOpen,
  Plus,
  Search,
  Sparkles,
  Layers,
  ArrowLeft,
  CheckCircle2,
  XCircle,
  RotateCw,
  Trash2,
  Send,
  Award,
  Clock,
  HelpCircle,
  FileText,
  AlertCircle,
} from 'lucide-react';
import './StudyStudio.css';

const rawApiBase =
  (import.meta as { env: { VITE_API_BASE?: string } }).env.VITE_API_BASE ??
  '/api/v1';
const API_BASE = rawApiBase.endsWith('/api/v1')
  ? rawApiBase
  : `${rawApiBase.replace(/\/+$/, '')}/api/v1`;

export interface StudyDeckItem {
  id: string;
  user_id: string;
  title: string;
  description?: string | null;
  subject: string;
  tags: string[];
  card_count: number;
  mastery_percentage: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface StudyCardItem {
  id: string;
  deck_id: string;
  user_id: string;
  front: string;
  back: string;
  explanation?: string | null;
  level: string;
  box: number;
  next_review_at?: string | null;
  last_reviewed_at?: string | null;
  review_count: number;
  correct_count: number;
}

export interface QuizQuestionItem {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface QuizSessionItem {
  id: string;
  title: string;
  topic: string;
  difficulty: string;
  score: number;
  total_questions: number;
  score_percentage: number;
  passed: boolean;
  completed_at?: string | null;
}

export interface StudyStats {
  total_decks: number;
  total_cards: number;
  cards_due_for_review: number;
  average_mastery: number;
  completed_quizzes: number;
  average_quiz_score: number;
}

interface StudyStudioProps {
  accessToken: string | null;
  onBack: () => void;
  onSendToChat?: (text: string) => void;
}

export const StudyStudio: React.FC<StudyStudioProps> = ({
  accessToken,
  onBack,
  onSendToChat,
}) => {
  const [activeTab, setActiveTab] = useState<'decks' | 'generator' | 'quiz'>('decks');

  // Decks & Cards State
  const [decks, setDecks] = useState<StudyDeckItem[]>([]);
  const [loadingDecks, setLoadingDecks] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSubject, setSelectedSubject] = useState('All');
  const [stats, setStats] = useState<StudyStats>({
    total_decks: 0,
    total_cards: 0,
    cards_due_for_review: 0,
    average_mastery: 0.0,
    completed_quizzes: 0,
    average_quiz_score: 0.0,
  });

  // Modals State
  const [showCreateDeckModal, setShowCreateDeckModal] = useState(false);
  const [newDeckTitle, setNewDeckTitle] = useState('');
  const [newDeckSubject, setNewDeckSubject] = useState('General');
  const [newDeckDesc, setNewDeckDesc] = useState('');
  const [newDeckTags, setNewDeckTags] = useState('');
  const [creatingDeck, setCreatingDeck] = useState(false);

  const [activeReviewDeck, setActiveReviewDeck] = useState<StudyDeckItem | null>(null);
  const [reviewCards, setReviewCards] = useState<StudyCardItem[]>([]);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [cardFlipped, setCardFlipped] = useState(false);
  const [loadingReview, setLoadingReview] = useState(false);

  const [addCardDeckId, setAddCardDeckId] = useState<string | null>(null);
  const [cardFront, setCardFront] = useState('');
  const [cardBack, setCardBack] = useState('');
  const [cardExpl, setCardExpl] = useState('');
  const [savingCard, setSavingCard] = useState(false);

  // Generator State
  const [genTopic, setGenTopic] = useState('');
  const [genSource, setGenSource] = useState('');
  const [genLevel, setGenLevel] = useState('intermediate');
  const [genCount, setGenCount] = useState(5);
  const [genDeckTarget, setGenDeckTarget] = useState('new');
  const [genExistingDeckId, setGenExistingDeckId] = useState('');
  const [generatingCards, setGeneratingCards] = useState(false);
  const [generatedCards, setGeneratedCards] = useState<
    Array<{ front: string; back: string; explanation?: string; tags?: string[] }>
  >([]);

  // Quiz State
  const [quizTopic, setQuizTopic] = useState('');
  const [quizSource, setQuizSource] = useState('');
  const [quizCount, setQuizCount] = useState(5);
  const [generatingQuiz, setGeneratingQuiz] = useState(false);
  const [activeQuizQuestions, setActiveQuizQuestions] = useState<QuizQuestionItem[]>([]);
  const [userQuizAnswers, setUserQuizAnswers] = useState<Record<string, number>>({});
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [quizResultScore, setQuizResultScore] = useState<number | null>(null);
  const [pastQuizzes, setPastQuizzes] = useState<QuizSessionItem[]>([]);

  const authHeaders = useMemo((): Record<string, string> => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };
    if (accessToken) {
      headers['Authorization'] = `Bearer ${accessToken}`;
    }
    return headers;
  }, [accessToken]);

  // Load Decks & Stats
  const loadDecksAndStats = useCallback(async () => {
    if (!accessToken) return;
    setLoadingDecks(true);
    setFetchError(null);
    try {
      const [dRes, sRes] = await Promise.all([
        fetch(`${API_BASE}/study/decks?limit=100`, { headers: authHeaders }),
        fetch(`${API_BASE}/study/stats`, { headers: authHeaders }),
      ]);
      if (dRes.ok) {
        const dData = await dRes.json();
        setDecks(dData.decks || []);
      } else {
        setFetchError('Failed to load study decks from the server.');
      }
      if (sRes.ok) {
        const sData = await sRes.json();
        setStats(sData);
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : 'Connection failed while loading study decks.');
    } finally {
      setLoadingDecks(false);
    }
  }, [accessToken, authHeaders]);

  const loadPastQuizzes = useCallback(async () => {
    if (!accessToken) return;
    try {
      const qRes = await fetch(`${API_BASE}/study/quizzes?limit=20`, { headers: authHeaders });
      if (qRes.ok) {
        const qData = await qRes.json();
        setPastQuizzes(qData.quizzes || []);
      }
    } catch {
      // Offline fallback
    }
  }, [accessToken, authHeaders]);

  useEffect(() => {
    loadDecksAndStats();
    loadPastQuizzes();
  }, [loadDecksAndStats, loadPastQuizzes]);

  // Create Deck
  const handleCreateDeck = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newDeckTitle.trim()) return;
    setCreatingDeck(true);
    try {
      const tags = newDeckTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await fetch(`${API_BASE}/study/decks`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          title: newDeckTitle.trim(),
          subject: newDeckSubject.trim() || 'General',
          description: newDeckDesc.trim() || null,
          tags,
        }),
      });
      if (res.ok) {
        setNewDeckTitle('');
        setNewDeckDesc('');
        setNewDeckTags('');
        setShowCreateDeckModal(false);
        await loadDecksAndStats();
      }
    } catch {
      // Offline
    } finally {
      setCreatingDeck(false);
    }
  };

  // Delete Deck (Optimistic with automatic rollback on error)
  const handleDeleteDeck = async (deckId: string) => {
    const previousDecks = [...decks];
    const previousStats = { ...stats };
    setDecks((prev) => prev.filter((d) => d.id !== deckId));
    setStats((prev) => ({
      ...prev,
      total_decks: Math.max(0, prev.total_decks - 1),
    }));

    try {
      const res = await fetch(`${API_BASE}/study/decks/${deckId}`, {
        method: 'DELETE',
        headers: authHeaders,
      });
      if (!res.ok) {
        throw new Error(`Failed to delete deck (HTTP ${res.status})`);
      }
      await loadDecksAndStats();
    } catch (err: unknown) {
      console.error('Delete deck failed, rolling back:', err);
      setDecks(previousDecks);
      setStats(previousStats);
      setFetchError(err instanceof Error ? err.message : 'Failed to delete study deck. Rolled back.');
    }
  };

  // Start Review Session
  const handleStartReview = async (deck: StudyDeckItem) => {
    setActiveReviewDeck(deck);
    setLoadingReview(true);
    setCurrentCardIndex(0);
    setCardFlipped(false);
    try {
      const res = await fetch(`${API_BASE}/study/decks/${deck.id}/cards`, {
        headers: authHeaders,
      });
      if (res.ok) {
        const data = await res.json();
        setReviewCards(data.cards || []);
      }
    } catch {
      setReviewCards([]);
    } finally {
      setLoadingReview(false);
    }
  };

  // Submit Card Review (Leitner Leitner spaced repetition)
  const handleReviewAnswer = async (isCorrect: boolean) => {
    const currentCard = reviewCards[currentCardIndex];
    if (!currentCard) return;

    try {
      const res = await fetch(`${API_BASE}/study/cards/${currentCard.id}/review`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({ is_correct: isCorrect }),
      });
      if (res.ok) {
        const updated = await res.json();
        setReviewCards((prev) =>
          prev.map((c, idx) => (idx === currentCardIndex ? updated : c))
        );
      }
    } catch {
      // Offline
    }

    setCardFlipped(false);
    if (currentCardIndex + 1 < reviewCards.length) {
      setCurrentCardIndex((i) => i + 1);
    } else {
      // Finished deck review
      await loadDecksAndStats();
      setActiveReviewDeck(null);
    }
  };

  // Add Card Manually
  const handleAddCard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addCardDeckId || !cardFront.trim() || !cardBack.trim()) return;
    setSavingCard(true);
    try {
      const res = await fetch(`${API_BASE}/study/decks/${addCardDeckId}/cards`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          front: cardFront.trim(),
          back: cardBack.trim(),
          explanation: cardExpl.trim() || null,
        }),
      });
      if (res.ok) {
        setCardFront('');
        setCardBack('');
        setCardExpl('');
        setAddCardDeckId(null);
        await loadDecksAndStats();
      }
    } catch {
      // Offline
    } finally {
      setSavingCard(false);
    }
  };

  // AI Flashcard Generation
  const handleGenerateCards = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!genTopic.trim()) return;
    setGeneratingCards(true);
    try {
      const payload: Record<string, unknown> = {
        topic: genTopic.trim(),
        source_text: genSource.trim() || null,
        level: genLevel,
        count: Number(genCount),
      };

      if (genDeckTarget === 'new') {
        payload.new_deck_title = `${genTopic.trim()} Deck`;
      } else if (genExistingDeckId) {
        payload.save_to_deck_id = genExistingDeckId;
      }

      const res = await fetch(`${API_BASE}/study/generate/flashcards`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        setGeneratedCards(data.cards || []);
        await loadDecksAndStats();
      }
    } catch {
      // Offline
    } finally {
      setGeneratingCards(false);
    }
  };

  // AI Quiz Generation
  const handleGenerateQuiz = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quizTopic.trim()) return;
    setGeneratingQuiz(true);
    setActiveQuizQuestions([]);
    setUserQuizAnswers({});
    setQuizSubmitted(false);
    setQuizResultScore(null);

    try {
      const res = await fetch(`${API_BASE}/study/generate/quiz`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          topic: quizTopic.trim(),
          source_text: quizSource.trim() || null,
          count: Number(quizCount),
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setActiveQuizQuestions(data.questions || []);
      }
    } catch {
      // Offline
    } finally {
      setGeneratingQuiz(false);
    }
  };

  // Submit Completed Quiz
  const handleSubmitQuiz = async () => {
    if (activeQuizQuestions.length === 0) return;
    let correct = 0;
    activeQuizQuestions.forEach((q, idx) => {
      if (userQuizAnswers[String(idx)] === q.correct_index) {
        correct++;
      }
    });

    setQuizResultScore(correct);
    setQuizSubmitted(true);

    try {
      await fetch(`${API_BASE}/study/quizzes`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify({
          title: `${quizTopic} Practice Quiz`,
          topic: quizTopic,
          questions: activeQuizQuestions,
          user_answers: userQuizAnswers,
        }),
      });
      await loadPastQuizzes();
      await loadDecksAndStats();
    } catch {
      // Offline
    }
  };

  // Distinct subjects for filter chips
  const subjectsList = useMemo(() => {
    const set = new Set<string>();
    decks.forEach((d) => {
      if (d.subject) set.add(d.subject);
    });
    return ['All', ...Array.from(set)];
  }, [decks]);

  // Filtered decks
  const filteredDecks = useMemo(() => {
    return decks.filter((d) => {
      const matchesSearch =
        !searchQuery ||
        d.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (d.description && d.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
        d.tags.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesSubject =
        selectedSubject === 'All' ||
        d.subject.toLowerCase() === selectedSubject.toLowerCase();

      return matchesSearch && matchesSubject;
    });
  }, [decks, searchQuery, selectedSubject]);

  return (
    <div className="study-studio">
      {/* Header */}
      <header className="study-studio__header">
        <div className="study-studio__header-left">
          <button type="button" className="study-studio__back-btn" onClick={onBack}>
            <ArrowLeft size={16} /> Back to Chat
          </button>
          <h1 className="study-studio__title">
            <BookOpen size={28} /> Study & Quiz Studio
          </h1>
          <p className="study-studio__desc">
            Active recall flashcards, Leitner spaced repetition, and AI practice quizzes.
          </p>
        </div>

        {/* Stats Bar */}
        <div className="study-studio__stats-bar">
          <div className="study-studio__stat-pill">
            <Layers size={16} />
            <span>Decks: <b>{stats.total_decks}</b></span>
          </div>
          <div className="study-studio__stat-pill">
            <FileText size={16} />
            <span>Cards: <b>{stats.total_cards}</b></span>
          </div>
          <div className="study-studio__stat-pill due">
            <Clock size={16} />
            <span>Due for Review: <b>{stats.cards_due_for_review}</b></span>
          </div>
          <div className="study-studio__stat-pill mastery">
            <Award size={16} />
            <span>Mastery: <b>{stats.average_mastery}%</b></span>
          </div>
        </div>
      </header>

      {/* Guest Mode Notice */}
      {!accessToken && (
        <div className="study-studio__auth-banner">
          <Award size={18} />
          <span>
            You are in <strong>Guest Mode</strong>. Active recall and local quizzes work, but saving decks, spaced repetition tracking, and cross-device sync require signing in.
          </span>
        </div>
      )}

      {/* Error Banner */}
      {fetchError && (
        <div className="study-studio__error-banner">
          <AlertCircle size={18} />
          <span style={{ flex: 1 }}>{fetchError}</span>
          <button
            type="button"
            className="study-studio__retry-btn"
            onClick={() => loadDecksAndStats()}
          >
            <RotateCw size={13} />
            <span>Retry Connection</span>
          </button>
        </div>
      )}

      {/* Tabs */}
      <nav className="study-studio__tabs">
        <button
          type="button"
          className={`study-studio__tab ${activeTab === 'decks' ? 'active' : ''}`}
          onClick={() => setActiveTab('decks')}
        >
          <Layers size={18} /> Flashcard Decks & Review
        </button>
        <button
          type="button"
          className={`study-studio__tab ${activeTab === 'generator' ? 'active' : ''}`}
          onClick={() => setActiveTab('generator')}
        >
          <Sparkles size={18} /> AI Study Generator
        </button>
        <button
          type="button"
          className={`study-studio__tab ${activeTab === 'quiz' ? 'active' : ''}`}
          onClick={() => setActiveTab('quiz')}
        >
          <HelpCircle size={18} /> Practice Quizzes
        </button>
      </nav>

      {/* Tab 1: Flashcard Decks */}
      {activeTab === 'decks' && (
        <section className="study-studio__content">
          <div className="study-studio__toolbar">
            <div className="study-studio__search-box">
              <Search size={16} color="#9ca3af" />
              <input
                type="text"
                placeholder="Search decks, tags, or concepts..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <button
              type="button"
              className="study-studio__primary-btn"
              onClick={() => setShowCreateDeckModal(true)}
            >
              <Plus size={16} /> New Study Deck
            </button>
          </div>

          {/* Subject Filter Pills */}
          {subjectsList.length > 1 && (
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
              {subjectsList.map((subj) => (
                <button
                  key={subj}
                  type="button"
                  onClick={() => setSelectedSubject(subj)}
                  style={{
                    background: selectedSubject === subj ? '#3b82f6' : 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    color: selectedSubject === subj ? '#fff' : '#9ca3af',
                    padding: '0.35rem 0.75rem',
                    borderRadius: '20px',
                    fontSize: '0.8rem',
                    cursor: 'pointer',
                  }}
                >
                  {subj}
                </button>
              ))}
            </div>
          )}

          {loadingDecks ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: '#9ca3af' }}>
              Loading study decks...
            </div>
          ) : filteredDecks.length === 0 ? (
            <div className="study-studio__empty">
              <div className="study-studio__empty-icon">🎴</div>
              <h3>No study decks found</h3>
              <p>
                Create your first study deck or use the AI Study Generator to extract flashcards from your lecture notes.
              </p>
              <div className="study-studio__empty-actions">
                <button
                  type="button"
                  className="study-studio__primary-btn"
                  onClick={() => setShowCreateDeckModal(true)}
                >
                  <Plus size={16} /> Create First Deck
                </button>
                <button
                  type="button"
                  className="study-studio__review-btn"
                  onClick={() => setActiveTab('generator')}
                >
                  <Sparkles size={16} /> Generate from Notes
                </button>
              </div>
            </div>
          ) : (
            <div className="study-studio__decks-grid">
              {filteredDecks.map((deck) => (
                <div key={deck.id} className="study-studio__deck-card">
                  <div>
                    <div className="study-studio__deck-top">
                      <span className="study-studio__subject-badge">{deck.subject}</span>
                      <button
                        type="button"
                        className="study-studio__secondary-icon-btn delete"
                        title="Delete Deck"
                        onClick={() => handleDeleteDeck(deck.id)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>

                    <h3 className="study-studio__deck-title">{deck.title}</h3>
                    {deck.description && (
                      <p className="study-studio__deck-desc">{deck.description}</p>
                    )}
                  </div>

                  {/* Tags */}
                  {deck.tags.length > 0 && (
                    <div className="study-studio__tags-list">
                      {deck.tags.map((t) => (
                        <span key={t} className="study-studio__tag">
                          #{t}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Mastery Progress Bar */}
                  <div className="study-studio__mastery-container">
                    <div className="study-studio__mastery-labels">
                      <span>{deck.card_count} flashcards</span>
                      <span>{deck.mastery_percentage}% mastery</span>
                    </div>
                    <div className="study-studio__mastery-bar-bg">
                      <div
                        className="study-studio__mastery-bar-fill"
                        style={{ width: `${Math.min(100, deck.mastery_percentage)}%` }}
                      />
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="study-studio__deck-actions">
                    <button
                      type="button"
                      className="study-studio__review-btn"
                      onClick={() => handleStartReview(deck)}
                      disabled={deck.card_count === 0}
                    >
                      <RotateCw size={15} /> Review Deck
                    </button>

                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <button
                        type="button"
                        className="study-studio__secondary-icon-btn"
                        title="Add Flashcard"
                        onClick={() => setAddCardDeckId(deck.id)}
                      >
                        <Plus size={16} />
                      </button>
                      {onSendToChat && (
                        <button
                          type="button"
                          className="study-studio__secondary-icon-btn"
                          title="Study with Roxy in Chat"
                          onClick={() => onSendToChat(`Let's study and review my flashcards for "${deck.title}".`)}
                        >
                          <Send size={15} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Tab 2: AI Study Generator */}
      {activeTab === 'generator' && (
        <section className="study-studio__content">
          <div className="study-studio__panel">
            <h3 style={{ margin: '0 0 1rem 0', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Sparkles size={20} color="#60a5fa" /> AI Flashcard Synthesis
            </h3>
            <form onSubmit={handleGenerateCards}>
              <div className="study-studio__form-grid">
                <div className="study-studio__form-group">
                  <label className="study-studio__label">Topic / Subject</label>
                  <input
                    type="text"
                    className="study-studio__input"
                    placeholder="e.g. Distributed Systems Consensus"
                    value={genTopic}
                    onChange={(e) => setGenTopic(e.target.value)}
                    required
                  />
                </div>

                <div className="study-studio__form-group">
                  <label className="study-studio__label">Difficulty Level</label>
                  <select
                    className="study-studio__select"
                    value={genLevel}
                    onChange={(e) => setGenLevel(e.target.value)}
                  >
                    <option value="beginner">Beginner (Foundations)</option>
                    <option value="intermediate">Intermediate (Standard)</option>
                    <option value="advanced">Advanced (Deep Dive)</option>
                  </select>
                </div>

                <div className="study-studio__form-group full">
                  <label className="study-studio__label">Source Notes / Context (Optional)</label>
                  <textarea
                    className="study-studio__textarea"
                    placeholder="Paste lecture notes, book excerpts, or concepts to extract specific flashcards..."
                    value={genSource}
                    onChange={(e) => setGenSource(e.target.value)}
                  />
                </div>

                <div className="study-studio__form-group">
                  <label className="study-studio__label">Card Count</label>
                  <select
                    className="study-studio__select"
                    value={genCount}
                    onChange={(e) => setGenCount(Number(e.target.value))}
                  >
                    <option value={3}>3 Flashcards</option>
                    <option value={5}>5 Flashcards</option>
                    <option value={10}>10 Flashcards</option>
                  </select>
                </div>

                <div className="study-studio__form-group">
                  <label className="study-studio__label">Save to Deck</label>
                  <select
                    className="study-studio__select"
                    value={genDeckTarget === 'new' ? 'new' : genExistingDeckId}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === 'new') {
                        setGenDeckTarget('new');
                        setGenExistingDeckId('');
                      } else {
                        setGenDeckTarget('existing');
                        setGenExistingDeckId(val);
                      }
                    }}
                  >
                    <option value="new">Create New Study Deck</option>
                    {decks.map((d) => (
                      <option key={d.id} value={d.id}>
                        Add to: {d.title}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="study-studio__primary-btn"
                disabled={generatingCards || !genTopic.trim()}
              >
                {generatingCards ? 'Synthesizing Cards...' : '⚡ Generate Flashcards'}
              </button>
            </form>
          </div>

          {/* Generated Cards Preview */}
          {generatedCards.length > 0 && (
            <div>
              <h4 style={{ color: '#fff', marginBottom: '1rem' }}>
                Generated Flashcards ({generatedCards.length})
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
                {generatedCards.map((c, i) => (
                  <div
                    key={i}
                    style={{
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '12px',
                      padding: '1rem',
                    }}
                  >
                    <div style={{ fontSize: '0.8rem', color: '#60a5fa', marginBottom: '0.4rem', fontWeight: 600 }}>
                      Card #{i + 1}
                    </div>
                    <div style={{ fontWeight: 600, color: '#fff', marginBottom: '0.5rem' }}>{c.front}</div>
                    <div style={{ fontSize: '0.9rem', color: '#34d399', marginBottom: '0.5rem' }}>{c.back}</div>
                    {c.explanation && (
                      <div style={{ fontSize: '0.8rem', color: '#9ca3af', fontStyle: 'italic' }}>
                        {c.explanation}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Tab 3: Practice Quizzes */}
      {activeTab === 'quiz' && (
        <section className="study-studio__content">
          <div className="study-studio__panel">
            <h3 style={{ margin: '0 0 1rem 0', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <HelpCircle size={20} color="#60a5fa" /> AI Practice Quiz Generator
            </h3>
            <form onSubmit={handleGenerateQuiz}>
              <div className="study-studio__form-grid">
                <div className="study-studio__form-group">
                  <label className="study-studio__label">Quiz Topic</label>
                  <input
                    type="text"
                    className="study-studio__input"
                    placeholder="e.g. Python AsyncIO & Event Loop"
                    value={quizTopic}
                    onChange={(e) => setQuizTopic(e.target.value)}
                    required
                  />
                </div>

                <div className="study-studio__form-group">
                  <label className="study-studio__label">Questions</label>
                  <select
                    className="study-studio__select"
                    value={quizCount}
                    onChange={(e) => setQuizCount(Number(e.target.value))}
                  >
                    <option value={3}>3 Questions</option>
                    <option value={5}>5 Questions</option>
                    <option value={10}>10 Questions</option>
                  </select>
                </div>

                <div className="study-studio__form-group full">
                  <label className="study-studio__label">Study Notes (Optional)</label>
                  <textarea
                    className="study-studio__textarea"
                    placeholder="Paste specific material to be quizzed on..."
                    value={quizSource}
                    onChange={(e) => setQuizSource(e.target.value)}
                  />
                </div>
              </div>

              <button
                type="submit"
                className="study-studio__primary-btn"
                disabled={generatingQuiz || !quizTopic.trim()}
              >
                {generatingQuiz ? 'Generating Quiz...' : '📝 Start Practice Quiz'}
              </button>
            </form>
          </div>

          {/* Active Quiz Player */}
          {activeQuizQuestions.length > 0 && (
            <div className="study-studio__quiz-runner">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3 style={{ color: '#fff', margin: 0 }}>Quiz: {quizTopic}</h3>
                {quizSubmitted && quizResultScore !== null && (
                  <span style={{ fontSize: '1.1rem', fontWeight: 700, color: quizResultScore / activeQuizQuestions.length >= 0.7 ? '#34d399' : '#f87171' }}>
                    Score: {quizResultScore} / {activeQuizQuestions.length} ({Math.round((quizResultScore / activeQuizQuestions.length) * 100)}%)
                  </span>
                )}
              </div>

              {activeQuizQuestions.map((q, qIdx) => {
                const selected = userQuizAnswers[String(qIdx)];
                return (
                  <div key={qIdx} className="study-studio__quiz-question-box">
                    <h4 className="study-studio__quiz-q-title">
                      {qIdx + 1}. {q.question}
                    </h4>

                    <div className="study-studio__quiz-options">
                      {q.options.map((opt, oIdx) => {
                        let optClass = 'study-studio__quiz-opt';
                        if (selected === oIdx) optClass += ' selected';
                        if (quizSubmitted) {
                          if (oIdx === q.correct_index) optClass += ' correct';
                          else if (selected === oIdx && oIdx !== q.correct_index) optClass += ' incorrect';
                        }
                        return (
                          <button
                            key={oIdx}
                            type="button"
                            className={optClass}
                            disabled={quizSubmitted}
                            onClick={() =>
                              setUserQuizAnswers((prev) => ({
                                ...prev,
                                [String(qIdx)]: oIdx,
                              }))
                            }
                          >
                            <span style={{ fontWeight: 700 }}>
                              {String.fromCharCode(65 + oIdx)}.
                            </span>
                            <span>{opt}</span>
                          </button>
                        );
                      })}
                    </div>

                    {quizSubmitted && (
                      <div className="study-studio__quiz-explanation">
                        <b>Explanation:</b> {q.explanation}
                      </div>
                    )}
                  </div>
                );
              })}

              {!quizSubmitted ? (
                <button
                  type="button"
                  className="study-studio__primary-btn"
                  style={{ alignSelf: 'flex-start' }}
                  onClick={handleSubmitQuiz}
                  disabled={Object.keys(userQuizAnswers).length === 0}
                >
                  <CheckCircle2 size={16} /> Submit & Check Answers
                </button>
              ) : (
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                  <button
                    type="button"
                    className="study-studio__review-btn"
                    onClick={() => {
                      setActiveQuizQuestions([]);
                      setUserQuizAnswers({});
                      setQuizSubmitted(false);
                      setQuizResultScore(null);
                    }}
                  >
                    Take Another Quiz
                  </button>
                  {onSendToChat && (
                    <button
                      type="button"
                      className="study-studio__primary-btn"
                      onClick={() =>
                        onSendToChat(
                          `I just scored ${quizResultScore}/${activeQuizQuestions.length} on my "${quizTopic}" quiz. Can you explain where I can improve?`
                        )
                      }
                    >
                      <Send size={16} /> Discuss with Roxy in Chat
                    </button>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Past Quiz Results */}
          {pastQuizzes.length > 0 && (
            <div style={{ marginTop: '2.5rem' }}>
              <h4 style={{ color: '#fff', marginBottom: '1rem' }}>Past Quiz Sessions</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                {pastQuizzes.map((pq) => (
                  <div
                    key={pq.id}
                    style={{
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid rgba(255, 255, 255, 0.08)',
                      borderRadius: '10px',
                      padding: '0.75rem 1rem',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, color: '#fff' }}>{pq.title}</div>
                      <div style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                        Topic: {pq.topic} • {pq.completed_at ? new Date(pq.completed_at).toLocaleDateString() : ''}
                      </div>
                    </div>
                    <span
                      style={{
                        fontWeight: 700,
                        color: pq.passed ? '#34d399' : '#f87171',
                      }}
                    >
                      {pq.score} / {pq.total_questions} ({pq.score_percentage}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* Modal: Create Deck */}
      {showCreateDeckModal && (
        <div className="study-studio__modal-overlay">
          <div className="study-studio__modal">
            <div className="study-studio__modal-header">
              <h3 className="study-studio__modal-title">Create New Study Deck</h3>
              <button
                type="button"
                className="study-studio__modal-close"
                onClick={() => setShowCreateDeckModal(false)}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleCreateDeck}>
              <div className="study-studio__modal-body">
                <div className="study-studio__form-group" style={{ marginBottom: '1rem' }}>
                  <label className="study-studio__label">Deck Title</label>
                  <input
                    type="text"
                    className="study-studio__input"
                    placeholder="e.g. Molecular Biology"
                    value={newDeckTitle}
                    onChange={(e) => setNewDeckTitle(e.target.value)}
                    required
                  />
                </div>

                <div className="study-studio__form-group" style={{ marginBottom: '1rem' }}>
                  <label className="study-studio__label">Subject</label>
                  <input
                    type="text"
                    className="study-studio__input"
                    placeholder="e.g. Biology, Computer Science, Law"
                    value={newDeckSubject}
                    onChange={(e) => setNewDeckSubject(e.target.value)}
                  />
                </div>

                <div className="study-studio__form-group" style={{ marginBottom: '1rem' }}>
                  <label className="study-studio__label">Description</label>
                  <textarea
                    className="study-studio__textarea"
                    placeholder="Brief description of the deck..."
                    value={newDeckDesc}
                    onChange={(e) => setNewDeckDesc(e.target.value)}
                  />
                </div>

                <div className="study-studio__form-group">
                  <label className="study-studio__label">Tags (comma-separated)</label>
                  <input
                    type="text"
                    className="study-studio__input"
                    placeholder="dna, rna, genetics"
                    value={newDeckTags}
                    onChange={(e) => setNewDeckTags(e.target.value)}
                  />
                </div>
              </div>
              <div
                style={{
                  padding: '1rem 1.5rem',
                  borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '0.75rem',
                }}
              >
                <button
                  type="button"
                  className="study-studio__back-btn"
                  onClick={() => setShowCreateDeckModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="study-studio__primary-btn"
                  disabled={creatingDeck || !newDeckTitle.trim()}
                >
                  {creatingDeck ? 'Creating...' : 'Create Deck'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Interactive Flashcard Reviewer */}
      {activeReviewDeck && (
        <div className="study-studio__modal-overlay">
          <div className="study-studio__modal" style={{ maxWidth: '640px' }}>
            <div className="study-studio__modal-header">
              <div>
                <h3 className="study-studio__modal-title">{activeReviewDeck.title}</h3>
                <span style={{ fontSize: '0.8rem', color: '#9ca3af' }}>
                  Card {currentCardIndex + 1} of {reviewCards.length}
                </span>
              </div>
              <button
                type="button"
                className="study-studio__modal-close"
                onClick={() => setActiveReviewDeck(null)}
              >
                &times;
              </button>
            </div>

            <div className="study-studio__modal-body">
              {loadingReview ? (
                <div style={{ textAlign: 'center', padding: '3rem', color: '#9ca3af' }}>
                  Loading flashcards...
                </div>
              ) : reviewCards.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                  <p>No cards found in this deck.</p>
                  <button
                    type="button"
                    className="study-studio__primary-btn"
                    onClick={() => {
                      setAddCardDeckId(activeReviewDeck.id);
                      setActiveReviewDeck(null);
                    }}
                  >
                    <Plus size={16} /> Add First Card
                  </button>
                </div>
              ) : (
                <>
                  <div className="study-studio__flashcard-player">
                    <div
                      className="study-studio__flashcard"
                      onClick={() => setCardFlipped((f) => !f)}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span className="study-studio__card-box-pill">
                          📦 Leitner Box {reviewCards[currentCardIndex]?.box || 1}
                        </span>
                        <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
                          Level: {reviewCards[currentCardIndex]?.level || 'intermediate'}
                        </span>
                      </div>

                      {!cardFlipped ? (
                        <div>
                          <div className="study-studio__card-prompt">
                            {reviewCards[currentCardIndex]?.front}
                          </div>
                          <div className="study-studio__card-flip-hint">
                            (Click card to reveal answer)
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div className="study-studio__card-answer">
                            {reviewCards[currentCardIndex]?.back}
                          </div>
                          {reviewCards[currentCardIndex]?.explanation && (
                            <div className="study-studio__card-expl">
                              {reviewCards[currentCardIndex].explanation}
                            </div>
                          )}
                        </div>
                      )}

                      <div style={{ display: 'flex', justifyContent: 'center' }}>
                        <span style={{ fontSize: '0.75rem', color: '#6b7280' }}>
                          {cardFlipped ? 'Answer Revealed' : 'Prompt / Concept'}
                        </span>
                      </div>
                    </div>
                  </div>

                  {cardFlipped && (
                    <div className="study-studio__review-controls">
                      <button
                        type="button"
                        className="study-studio__btn-wrong"
                        onClick={() => handleReviewAnswer(false)}
                      >
                        <XCircle size={18} /> Forgot (Reset to Box 1)
                      </button>
                      <button
                        type="button"
                        className="study-studio__btn-correct"
                        onClick={() => handleReviewAnswer(true)}
                      >
                        <CheckCircle2 size={18} /> Got it Right (Advance Box)
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal: Add Card Manually */}
      {addCardDeckId && (
        <div className="study-studio__modal-overlay">
          <div className="study-studio__modal">
            <div className="study-studio__modal-header">
              <h3 className="study-studio__modal-title">Add Flashcard</h3>
              <button
                type="button"
                className="study-studio__modal-close"
                onClick={() => setAddCardDeckId(null)}
              >
                &times;
              </button>
            </div>
            <form onSubmit={handleAddCard}>
              <div className="study-studio__modal-body">
                <div className="study-studio__form-group" style={{ marginBottom: '1rem' }}>
                  <label className="study-studio__label">Front (Concept / Question)</label>
                  <textarea
                    className="study-studio__textarea"
                    placeholder="e.g. What is the difference between synchronous and asynchronous code?"
                    value={cardFront}
                    onChange={(e) => setCardFront(e.target.value)}
                    required
                  />
                </div>

                <div className="study-studio__form-group" style={{ marginBottom: '1rem' }}>
                  <label className="study-studio__label">Back (Answer / Definition)</label>
                  <textarea
                    className="study-studio__textarea"
                    placeholder="e.g. Synchronous executes sequentially; asynchronous allows operations to run without blocking."
                    value={cardBack}
                    onChange={(e) => setCardBack(e.target.value)}
                    required
                  />
                </div>

                <div className="study-studio__form-group">
                  <label className="study-studio__label">Explanation / Memory Hook (Optional)</label>
                  <input
                    type="text"
                    className="study-studio__input"
                    placeholder="e.g. Think of a single chef vs multiple kitchen stations."
                    value={cardExpl}
                    onChange={(e) => setCardExpl(e.target.value)}
                  />
                </div>
              </div>
              <div
                style={{
                  padding: '1rem 1.5rem',
                  borderTop: '1px solid rgba(255, 255, 255, 0.08)',
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: '0.75rem',
                }}
              >
                <button
                  type="button"
                  className="study-studio__back-btn"
                  onClick={() => setAddCardDeckId(null)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="study-studio__primary-btn"
                  disabled={savingCard || !cardFront.trim() || !cardBack.trim()}
                >
                  {savingCard ? 'Saving...' : 'Add Card'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default StudyStudio;
