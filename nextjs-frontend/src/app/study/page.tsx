"use client";

import React, { useState, useEffect, useCallback, useMemo } from "react";

interface StudyDeckItem {
  id: string;
  user_id?: string;
  title: string;
  description?: string | null;
  subject: string;
  tags?: string[];
  card_count: number;
  mastery_percentage: number;
  created_at?: string | null;
  updated_at?: string | null;
}

interface StudyCardItem {
  id: string;
  deck_id: string;
  user_id?: string;
  front: string;
  back: string;
  explanation?: string | null;
  level?: string;
  box: number;
  next_review_at?: string | null;
  last_reviewed_at?: string | null;
  review_count?: number;
  correct_count?: number;
}

interface QuizQuestionItem {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

interface QuizSessionItem {
  id: string;
  title: string;
  topic: string;
  difficulty?: string;
  score: number;
  total_questions: number;
  score_percentage: number;
  passed: boolean;
  completed_at?: string | null;
}

interface StudyStats {
  total_decks: number;
  total_cards: number;
  cards_due_for_review: number;
  average_mastery: number;
  completed_quizzes?: number;
  average_quiz_score?: number;
}

const rawApiBase = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api/v1";
const API_BASE = rawApiBase.endsWith("/api/v1") ? rawApiBase : `${rawApiBase}/api/v1`;

export default function StudyStudioPage() {
  const [activeTab, setActiveTab] = useState<"decks" | "generator" | "quiz">("decks");
  const [accessToken, setAccessToken] = useState<string | null>(null);

  // Decks & Stats
  const [decks, setDecks] = useState<StudyDeckItem[]>([]);
  const [loadingDecks, setLoadingDecks] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSubject, setSelectedSubject] = useState("All");
  const [stats, setStats] = useState<StudyStats>({
    total_decks: 0,
    total_cards: 0,
    cards_due_for_review: 0,
    average_mastery: 0.0,
  });

  // Deck Creation Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newSubject, setNewSubject] = useState("General");
  const [newDesc, setNewDesc] = useState("");
  const [newTags, setNewTags] = useState("");
  const [isCreatingDeck, setIsCreatingDeck] = useState(false);

  // Review Session Modal (Leitner Spaced Repetition)
  const [activeReviewDeck, setActiveReviewDeck] = useState<StudyDeckItem | null>(null);
  const [reviewCards, setReviewCards] = useState<StudyCardItem[]>([]);
  const [currentCardIndex, setCurrentCardIndex] = useState(0);
  const [cardFlipped, setCardFlipped] = useState(false);
  const [loadingReview, setLoadingReview] = useState(false);

  // Add Card Modal
  const [addCardDeckId, setAddCardDeckId] = useState<string | null>(null);
  const [cardFront, setCardFront] = useState("");
  const [cardBack, setCardBack] = useState("");
  const [cardExpl, setCardExpl] = useState("");
  const [isSavingCard, setIsSavingCard] = useState(false);

  // Generator State
  const [genTopic, setGenTopic] = useState("");
  const [genSource, setGenSource] = useState("");
  const [genLevel, setGenLevel] = useState("intermediate");
  const [genCount, setGenCount] = useState(5);
  const [genDeckTarget, setGenDeckTarget] = useState<"new" | "existing">("new");
  const [genExistingDeckId, setGenExistingDeckId] = useState("");
  const [isGeneratingCards, setIsGeneratingCards] = useState(false);
  const [generatedCards, setGeneratedCards] = useState<
    Array<{ front: string; back: string; explanation?: string; tags?: string[] }>
  >([]);

  // Quiz State
  const [quizTopic, setQuizTopic] = useState("");
  const [quizSource, setQuizSource] = useState("");
  const [quizCount, setQuizCount] = useState(5);
  const [isGeneratingQuiz, setIsGeneratingQuiz] = useState(false);
  const [activeQuizQuestions, setActiveQuizQuestions] = useState<QuizQuestionItem[]>([]);
  const [userQuizAnswers, setUserQuizAnswers] = useState<Record<string, number>>({});
  const [quizSubmitted, setQuizSubmitted] = useState(false);
  const [quizScore, setQuizScore] = useState<number | null>(null);
  const [pastQuizzes, setPastQuizzes] = useState<QuizSessionItem[]>([]);

  // Alerts & Notifications
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const showNotice = (msg: string) => {
    setNotice(msg);
    setTimeout(() => setNotice((curr) => (curr === msg ? null : curr)), 4000);
  };

  useEffect(() => {
    if (typeof window !== "undefined") {
      const tok = localStorage.getItem("roxy_access_token") || localStorage.getItem("access_token");
      setAccessToken(tok);
    }
  }, []);

  const authHeaders = useMemo((): Record<string, string> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
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
        setFetchError("Unable to load study decks from the server.");
      }
      if (sRes.ok) {
        const sData = await sRes.json();
        setStats(sData);
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Connection failed while loading study decks.");
    } finally {
      setLoadingDecks(false);
    }
  }, [accessToken, authHeaders]);

  // Load Past Quizzes
  const loadPastQuizzes = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${API_BASE}/study/quizzes?limit=20`, { headers: authHeaders });
      if (res.ok) {
        const data = await res.json();
        setPastQuizzes(data.quizzes || []);
      }
    } catch {
      // Offline fallback
    }
  }, [accessToken, authHeaders]);

  useEffect(() => {
    if (accessToken) {
      loadDecksAndStats();
      loadPastQuizzes();
    }
  }, [accessToken, loadDecksAndStats, loadPastQuizzes]);

  // Create Deck
  const handleCreateDeck = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setIsCreatingDeck(true);
    try {
      const tags = newTags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      const res = await fetch(`${API_BASE}/study/decks`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          title: newTitle.trim(),
          subject: newSubject.trim() || "General",
          description: newDesc.trim() || null,
          tags,
        }),
      });

      if (res.ok) {
        setNewTitle("");
        setNewDesc("");
        setNewTags("");
        setShowCreateModal(false);
        showNotice("Study deck created successfully!");
        await loadDecksAndStats();
      } else {
        throw new Error("Failed to create study deck.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Failed to create study deck.");
    } finally {
      setIsCreatingDeck(false);
    }
  };

  // Delete Deck with Optimistic Rollback
  const handleDeleteDeck = async (deckId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const prevDecks = [...decks];
    const prevStats = { ...stats };
    setDecks((curr) => curr.filter((d) => d.id !== deckId));
    setStats((curr) => ({
      ...curr,
      total_decks: Math.max(0, curr.total_decks - 1),
    }));

    try {
      const res = await fetch(`${API_BASE}/study/decks/${deckId}`, {
        method: "DELETE",
        headers: authHeaders,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      showNotice("Study deck deleted.");
      await loadDecksAndStats();
    } catch (err) {
      console.error("Delete deck failed, rolling back:", err);
      setDecks(prevDecks);
      setStats(prevStats);
      setFetchError("Failed to delete study deck. Changes rolled back.");
    }
  };

  // Start Review Session
  const handleStartReview = async (deck: StudyDeckItem) => {
    setActiveReviewDeck(deck);
    setLoadingReview(true);
    setCurrentCardIndex(0);
    setCardFlipped(false);
    try {
      const res = await fetch(`${API_BASE}/study/decks/${deck.id}/cards`, { headers: authHeaders });
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

  // Leitner Review Step
  const handleReviewAnswer = async (isCorrect: boolean) => {
    const card = reviewCards[currentCardIndex];
    if (!card) return;

    try {
      const res = await fetch(`${API_BASE}/study/cards/${card.id}/review`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({ is_correct: isCorrect }),
      });
      if (res.ok) {
        const updated = await res.json();
        setReviewCards((prev) => prev.map((c, idx) => (idx === currentCardIndex ? updated : c)));
      }
    } catch {
      // Offline fallback
    }

    setCardFlipped(false);
    if (currentCardIndex + 1 < reviewCards.length) {
      setCurrentCardIndex((i) => i + 1);
    } else {
      showNotice("Deck review session completed!");
      await loadDecksAndStats();
      setActiveReviewDeck(null);
    }
  };

  // Add Card Manually
  const handleAddCard = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!addCardDeckId || !cardFront.trim() || !cardBack.trim()) return;
    setIsSavingCard(true);
    try {
      const res = await fetch(`${API_BASE}/study/decks/${addCardDeckId}/cards`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify({
          front: cardFront.trim(),
          back: cardBack.trim(),
          explanation: cardExpl.trim() || null,
        }),
      });
      if (res.ok) {
        setCardFront("");
        setCardBack("");
        setCardExpl("");
        setAddCardDeckId(null);
        showNotice("Flashcard added to deck!");
        await loadDecksAndStats();
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Failed to add flashcard.");
    } finally {
      setIsSavingCard(false);
    }
  };

  // AI Flashcard Generation
  const handleGenerateCards = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!genTopic.trim()) return;
    setIsGeneratingCards(true);
    try {
      const payload: Record<string, unknown> = {
        topic: genTopic.trim(),
        source_text: genSource.trim() || null,
        level: genLevel,
        count: Number(genCount),
      };

      if (genDeckTarget === "new") {
        payload.new_deck_title = `${genTopic.trim()} Deck`;
      } else if (genExistingDeckId) {
        payload.save_to_deck_id = genExistingDeckId;
      }

      const res = await fetch(`${API_BASE}/study/generate/flashcards`, {
        method: "POST",
        headers: authHeaders,
        body: JSON.stringify(payload),
      });

      if (res.ok) {
        const data = await res.json();
        setGeneratedCards(data.cards || []);
        showNotice(`Generated ${data.cards?.length || 0} flashcards!`);
        await loadDecksAndStats();
      } else {
        throw new Error("Failed to synthesize flashcards.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Flashcard synthesis failed.");
    } finally {
      setIsGeneratingCards(false);
    }
  };

  // AI Quiz Generation
  const handleGenerateQuiz = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quizTopic.trim()) return;
    setIsGeneratingQuiz(true);
    setActiveQuizQuestions([]);
    setUserQuizAnswers({});
    setQuizSubmitted(false);
    setQuizScore(null);

    try {
      const res = await fetch(`${API_BASE}/study/generate/quiz`, {
        method: "POST",
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
        showNotice("Practice quiz generated!");
      } else {
        throw new Error("Failed to generate practice quiz.");
      }
    } catch (err: unknown) {
      setFetchError(err instanceof Error ? err.message : "Quiz generation failed.");
    } finally {
      setIsGeneratingQuiz(false);
    }
  };

  // Submit Completed Quiz
  const handleSubmitQuiz = async () => {
    if (activeQuizQuestions.length === 0) return;
    let correct = 0;
    activeQuizQuestions.forEach((q, idx) => {
      if (userQuizAnswers[String(idx)] === q.correct_index) correct++;
    });

    setQuizScore(correct);
    setQuizSubmitted(true);

    try {
      await fetch(`${API_BASE}/study/quizzes`, {
        method: "POST",
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
      // Offline fallback
    }
  };

  // Subject filter list
  const subjectsList = useMemo(() => {
    const set = new Set<string>();
    decks.forEach((d) => {
      if (d.subject) set.add(d.subject);
    });
    return ["All", ...Array.from(set)];
  }, [decks]);

  // Filtered decks
  const filteredDecks = useMemo(() => {
    return decks.filter((d) => {
      const matchSearch =
        !searchQuery ||
        d.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (d.description && d.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (d.tags && d.tags.some((t) => t.toLowerCase().includes(searchQuery.toLowerCase())));
      const matchSubj = selectedSubject === "All" || d.subject.toLowerCase() === selectedSubject.toLowerCase();
      return matchSearch && matchSubj;
    });
  }, [decks, searchQuery, selectedSubject]);

  return (
    <div className="min-h-screen bg-[#f8faf9] text-slate-800 pb-16">
      {/* Top Header */}
      <div className="bg-white border-b border-slate-200 sticky top-16 z-20">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <span className="text-2xl p-2 rounded-xl bg-teal-50 border border-teal-200">🎓</span>
                <div>
                  <h1 className="text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
                    Study & Learning Studio
                    <span className="text-xs px-2 py-0.5 rounded-full bg-teal-100 text-[#0d9488] font-semibold">
                      Spaced Repetition
                    </span>
                  </h1>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Active recall flashcard decks, Leitner 5-box spaced repetition, and AI-powered practice quizzes
                  </p>
                </div>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200 text-xs font-medium self-start sm:self-auto">
              <button
                onClick={() => setActiveTab("decks")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "decks"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>🎴</span>
                <span>Flashcards & Review</span>
              </button>
              <button
                onClick={() => setActiveTab("generator")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "generator"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>⚡</span>
                <span>AI Generator</span>
              </button>
              <button
                onClick={() => setActiveTab("quiz")}
                className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 ${
                  activeTab === "quiz"
                    ? "bg-white text-[#0d9488] font-semibold shadow-sm"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <span>📝</span>
                <span>Practice Quizzes</span>
              </button>
            </div>
          </div>

          {/* Stats Bar */}
          <div className="mt-5 pt-4 border-t border-slate-100 flex items-center gap-4 flex-wrap text-xs">
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
              <span className="text-slate-400">📚</span>
              <span className="text-slate-600 font-medium">Decks:</span>
              <strong className="text-slate-900 font-bold">{stats.total_decks}</strong>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl">
              <span className="text-slate-400">🎴</span>
              <span className="text-slate-600 font-medium">Total Cards:</span>
              <strong className="text-slate-900 font-bold">{stats.total_cards}</strong>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-xl text-amber-800">
              <span>⏰</span>
              <span className="font-medium">Due for Review:</span>
              <strong className="font-bold">{stats.cards_due_for_review}</strong>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800">
              <span>🏆</span>
              <span className="font-medium">Average Mastery:</span>
              <strong className="font-bold">{stats.average_mastery}%</strong>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 mt-6">
        {/* Guest Auth Notice */}
        {!accessToken && (
          <div className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 text-xs flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-base">🛡️</span>
              <span>
                <strong>Guest Mode:</strong> You can practice flashcards and generate quizzes locally, but persistent deck saving and Leitner spaced repetition tracking require signing in.
              </span>
            </div>
            <a
              href="/"
              className="px-3 py-1 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 transition-colors whitespace-nowrap"
            >
              Sign In
            </a>
          </div>
        )}

        {/* Global Error Banner */}
        {fetchError && (
          <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-xs flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="text-base">⚠️</span>
              <span>{fetchError}</span>
            </div>
            <button
              onClick={() => {
                setFetchError(null);
                loadDecksAndStats();
              }}
              className="px-2.5 py-1 bg-red-100 hover:bg-red-200 text-red-800 rounded-md font-medium transition-colors"
            >
              ↻ Retry Connection
            </button>
          </div>
        )}

        {/* Notice alert */}
        {notice && (
          <div className="mb-6 p-3 rounded-xl bg-teal-50 border border-teal-200 text-[#0d9488] text-xs flex items-center gap-2">
            <span>✨</span>
            <span>{notice}</span>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 1: FLASHCARD DECKS & REVIEW                                          */}
        {/* ========================================================================= */}
        {activeTab === "decks" && (
          <div className="space-y-6">
            {/* Toolbar */}
            <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-sm flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
              <div className="relative flex-1 sm:max-w-md">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search decks by title, description, or tags..."
                  className="w-full pl-10 pr-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                />
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(true)}
                  className="px-4 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl text-xs font-semibold transition-all shadow-sm flex items-center gap-1.5"
                >
                  <span>＋</span>
                  <span>New Study Deck</span>
                </button>
                <button
                  type="button"
                  onClick={loadDecksAndStats}
                  className="p-2 bg-slate-100 hover:bg-slate-200 text-slate-600 rounded-xl text-xs transition-colors"
                  title="Refresh decks"
                >
                  ↻
                </button>
              </div>
            </div>

            {/* Subject Filters */}
            {subjectsList.length > 1 && (
              <div className="flex items-center gap-1.5 flex-wrap text-xs">
                <span className="text-slate-400 font-medium mr-1">Subject:</span>
                {subjectsList.map((subj) => (
                  <button
                    key={subj}
                    onClick={() => setSelectedSubject(subj)}
                    className={`px-3 py-1 rounded-lg transition-colors ${
                      selectedSubject === subj
                        ? "bg-[#0d9488] text-white font-semibold shadow-sm"
                        : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {subj}
                  </button>
                ))}
              </div>
            )}

            {/* Decks Grid */}
            {loadingDecks ? (
              <div className="py-20 text-center text-xs text-slate-500">
                <span className="inline-block animate-spin text-xl mb-2">↻</span>
                <p>Loading study decks and mastery stats…</p>
              </div>
            ) : filteredDecks.length === 0 ? (
              <div className="bg-white rounded-2xl border border-dashed border-slate-200 p-12 text-center">
                <span className="text-4xl block mb-2">🎴</span>
                <h3 className="text-base font-bold text-slate-800">No Study Decks Found</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-4">
                  {searchQuery || selectedSubject !== "All"
                    ? "No decks match your active filters."
                    : "Create your first study deck or synthesize flashcards automatically from lecture notes."}
                </p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={() => setShowCreateModal(true)}
                    className="px-4 py-2 bg-[#0d9488] text-white rounded-xl text-xs font-semibold hover:bg-[#0f766e] transition-colors"
                  >
                    Create First Deck
                  </button>
                  <button
                    onClick={() => setActiveTab("generator")}
                    className="px-4 py-2 bg-slate-100 text-slate-700 rounded-xl text-xs font-semibold hover:bg-slate-200 transition-colors"
                  >
                    Generate from Notes
                  </button>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {filteredDecks.map((deck) => (
                  <div
                    key={deck.id}
                    className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-teal-50 text-[#0d9488] border border-teal-200">
                          {deck.subject}
                        </span>
                        <button
                          type="button"
                          onClick={(e) => handleDeleteDeck(deck.id, e)}
                          className="text-slate-400 hover:text-red-600 transition-colors text-xs"
                          title="Delete Deck"
                        >
                          🗑️
                        </button>
                      </div>

                      <h3 className="text-sm font-bold text-slate-900 mb-1 line-clamp-1">{deck.title}</h3>
                      {deck.description && (
                        <p className="text-xs text-slate-500 mb-3 line-clamp-2">{deck.description}</p>
                      )}

                      {deck.tags && deck.tags.length > 0 && (
                        <div className="flex items-center gap-1 flex-wrap mb-3">
                          {deck.tags.map((t) => (
                            <span key={t} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-600">
                              #{t}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="pt-4 border-t border-slate-100 space-y-3">
                      {/* Mastery Progress */}
                      <div>
                        <div className="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                          <span>{deck.card_count} flashcards</span>
                          <span className="font-semibold text-slate-700">{deck.mastery_percentage}% mastery</span>
                        </div>
                        <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                          <div
                            className="bg-[#0d9488] h-full rounded-full transition-all"
                            style={{ width: `${Math.min(100, deck.mastery_percentage)}%` }}
                          />
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center justify-between gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => handleStartReview(deck)}
                          disabled={deck.card_count === 0}
                          className="flex-1 py-1.5 bg-teal-50 hover:bg-teal-100 text-[#0d9488] rounded-lg text-xs font-semibold transition-colors flex items-center justify-center gap-1.5 disabled:opacity-40"
                        >
                          <span>↻</span>
                          <span>Review Deck</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setAddCardDeckId(deck.id)}
                          className="p-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs transition-colors"
                          title="Add Card"
                        >
                          ＋
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: AI FLASHCARD GENERATOR                                            */}
        {/* ========================================================================= */}
        {activeTab === "generator" && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
              <div>
                <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <span>⚡</span>
                  <span>AI Flashcard Synthesis</span>
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Generate active recall question-answer pairs from raw concepts or notes
                </p>
              </div>

              <form onSubmit={handleGenerateCards} className="space-y-4 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">Topic / Concept</label>
                  <input
                    type="text"
                    value={genTopic}
                    onChange={(e) => setGenTopic(e.target.value)}
                    placeholder="e.g., PostgreSQL indexing strategies, Mitosis stages, Constitutional Law"
                    required
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">Difficulty</label>
                    <select
                      value={genLevel}
                      onChange={(e) => setGenLevel(e.target.value)}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    >
                      <option value="beginner">Beginner</option>
                      <option value="intermediate">Intermediate</option>
                      <option value="advanced">Advanced</option>
                    </select>
                  </div>
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1.5">Card Count</label>
                    <select
                      value={genCount}
                      onChange={(e) => setGenCount(Number(e.target.value))}
                      className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                    >
                      <option value={3}>3 Cards</option>
                      <option value={5}>5 Cards</option>
                      <option value={10}>10 Cards</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">Source Notes (Optional)</label>
                  <textarea
                    rows={4}
                    value={genSource}
                    onChange={(e) => setGenSource(e.target.value)}
                    placeholder="Paste lecture excerpts or notes to ground generated cards..."
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  />
                </div>

                <div>
                  <label className="block font-semibold text-slate-700 mb-1.5">Target Deck</label>
                  <select
                    value={genDeckTarget === "new" ? "new" : genExistingDeckId}
                    onChange={(e) => {
                      const val = e.target.value;
                      if (val === "new") {
                        setGenDeckTarget("new");
                        setGenExistingDeckId("");
                      } else {
                        setGenDeckTarget("existing");
                        setGenExistingDeckId(val);
                      }
                    }}
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-[#0d9488]/30"
                  >
                    <option value="new">Create New Deck automatically</option>
                    {decks.map((d) => (
                      <option key={d.id} value={d.id}>
                        Add to: {d.title}
                      </option>
                    ))}
                  </select>
                </div>

                <button
                  type="submit"
                  disabled={isGeneratingCards || !genTopic.trim()}
                  className="w-full py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {isGeneratingCards ? (
                    <>
                      <span className="inline-block animate-spin">↻</span>
                      <span>Synthesizing Flashcards…</span>
                    </>
                  ) : (
                    <>
                      <span>⚡</span>
                      <span>Generate Flashcards</span>
                    </>
                  )}
                </button>
              </form>
            </div>

            {/* Generated Cards Preview */}
            <div className="lg:col-span-6 bg-white rounded-2xl border border-slate-200 p-6 shadow-sm flex flex-col">
              <h3 className="text-sm font-bold text-slate-900 pb-3 border-b border-slate-100 flex items-center justify-between">
                <span>Preview Generated Cards</span>
                <span className="text-xs font-normal text-slate-500">
                  {generatedCards.length > 0 ? `${generatedCards.length} Cards` : ""}
                </span>
              </h3>

              <div className="flex-1 mt-4 overflow-y-auto max-h-[500px] space-y-3">
                {generatedCards.length > 0 ? (
                  generatedCards.map((c, i) => (
                    <div key={i} className="p-4 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1.5">
                      <div className="font-semibold text-slate-900">Q: {c.front}</div>
                      <div className="text-emerald-700 font-medium">A: {c.back}</div>
                      {c.explanation && <div className="text-slate-500 italic">💡 {c.explanation}</div>}
                    </div>
                  ))
                ) : (
                  <div className="h-full flex flex-col items-center justify-center py-16 text-slate-400 text-xs text-center">
                    <span className="text-3xl mb-2">🎴</span>
                    <p>No cards synthesized yet.</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      Fill out the topic form on the left and click Generate.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: PRACTICE QUIZZES                                                   */}
        {/* ========================================================================= */}
        {activeTab === "quiz" && (
          <div className="space-y-6">
            {/* Quiz Generator Bar */}
            <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
              <h2 className="text-base font-bold text-slate-900 mb-3 flex items-center gap-2">
                <span>📝</span>
                <span>AI Practice Quiz Generator</span>
              </h2>
              <form onSubmit={handleGenerateQuiz} className="grid grid-cols-1 sm:grid-cols-12 gap-3 text-xs">
                <div className="sm:col-span-6">
                  <input
                    type="text"
                    value={quizTopic}
                    onChange={(e) => setQuizTopic(e.target.value)}
                    placeholder="Enter quiz topic (e.g. Python AsyncIO, Cell Division)..."
                    required
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                  />
                </div>
                <div className="sm:col-span-3">
                  <select
                    value={quizCount}
                    onChange={(e) => setQuizCount(Number(e.target.value))}
                    className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-[#0d9488]"
                  >
                    <option value={3}>3 Questions</option>
                    <option value={5}>5 Questions</option>
                    <option value={10}>10 Questions</option>
                  </select>
                </div>
                <div className="sm:col-span-3">
                  <button
                    type="submit"
                    disabled={isGeneratingQuiz || !quizTopic.trim()}
                    className="w-full py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50"
                  >
                    {isGeneratingQuiz ? "Generating…" : "Start Quiz"}
                  </button>
                </div>
              </form>
            </div>

            {/* Active Quiz Player */}
            {activeQuizQuestions.length > 0 && (
              <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <h3 className="text-sm font-bold text-slate-900">Quiz: {quizTopic}</h3>
                  {quizSubmitted && quizScore !== null && (
                    <span
                      className={`text-sm font-bold px-3 py-1 rounded-full ${
                        quizScore / activeQuizQuestions.length >= 0.7
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-red-100 text-red-800"
                      }`}
                    >
                      Score: {quizScore} / {activeQuizQuestions.length} (
                      {Math.round((quizScore / activeQuizQuestions.length) * 100)}%)
                    </span>
                  )}
                </div>

                <div className="space-y-6">
                  {activeQuizQuestions.map((q, qIdx) => {
                    const selected = userQuizAnswers[String(qIdx)];
                    return (
                      <div key={qIdx} className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-3 text-xs">
                        <h4 className="font-bold text-slate-800 text-sm">
                          {qIdx + 1}. {q.question}
                        </h4>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {q.options.map((opt, oIdx) => {
                            let btnStyle = "bg-white border-slate-200 text-slate-700 hover:bg-slate-100";
                            if (selected === oIdx) btnStyle = "bg-teal-50 border-[#0d9488] text-[#0d9488] font-semibold";
                            if (quizSubmitted) {
                              if (oIdx === q.correct_index) btnStyle = "bg-emerald-100 border-emerald-400 text-emerald-900 font-bold";
                              else if (selected === oIdx && oIdx !== q.correct_index)
                                btnStyle = "bg-red-100 border-red-300 text-red-800";
                            }

                            return (
                              <button
                                key={oIdx}
                                type="button"
                                disabled={quizSubmitted}
                                onClick={() =>
                                  setUserQuizAnswers((prev) => ({
                                    ...prev,
                                    [String(qIdx)]: oIdx,
                                  }))
                                }
                                className={`p-3 rounded-xl border text-left transition-all flex items-start gap-2 ${btnStyle}`}
                              >
                                <span className="font-mono font-bold text-slate-400">
                                  {String.fromCharCode(65 + oIdx)}.
                                </span>
                                <span>{opt}</span>
                              </button>
                            );
                          })}
                        </div>

                        {quizSubmitted && (
                          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-emerald-900">
                            <strong>Explanation:</strong> {q.explanation}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                <div className="pt-2 flex items-center gap-3">
                  {!quizSubmitted ? (
                    <button
                      type="button"
                      onClick={handleSubmitQuiz}
                      disabled={Object.keys(userQuizAnswers).length === 0}
                      className="px-6 py-2.5 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl text-xs font-semibold transition-all shadow-sm disabled:opacity-50"
                    >
                      Submit & Check Answers
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setActiveQuizQuestions([]);
                        setUserQuizAnswers({});
                        setQuizSubmitted(false);
                        setQuizScore(null);
                      }}
                      className="px-6 py-2.5 bg-slate-800 hover:bg-slate-900 text-white rounded-xl text-xs font-semibold transition-all shadow-sm"
                    >
                      Take Another Quiz
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Past Quizzes Table */}
            {pastQuizzes.length > 0 && (
              <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
                <h3 className="text-sm font-bold text-slate-900 mb-4">Past Quiz Sessions</h3>
                <div className="divide-y divide-slate-100">
                  {pastQuizzes.map((pq) => (
                    <div key={pq.id} className="py-3 flex items-center justify-between text-xs">
                      <div>
                        <span className="font-semibold text-slate-900 block">{pq.title}</span>
                        <span className="text-[11px] text-slate-400">
                          {pq.topic} • {pq.completed_at ? new Date(pq.completed_at).toLocaleDateString() : "Recent"}
                        </span>
                      </div>
                      <span
                        className={`font-bold px-2.5 py-0.5 rounded-full text-[11px] ${
                          pq.passed ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-800"
                        }`}
                      >
                        {pq.score} / {pq.total_questions} ({pq.score_percentage}%)
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Modal: Create Deck */}
      {showCreateModal && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setShowCreateModal(false)}
        >
          <div
            className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-bold text-slate-900 mb-4">Create Study Deck</h3>
            <form onSubmit={handleCreateDeck} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Deck Title</label>
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="e.g. Distributed Consensus Algorithms"
                  required
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Subject</label>
                <input
                  type="text"
                  value={newSubject}
                  onChange={(e) => setNewSubject(e.target.value)}
                  placeholder="e.g. Computer Science, Medicine, Law"
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Description</label>
                <textarea
                  rows={3}
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  placeholder="Brief overview of the material covered..."
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Tags (Comma-Separated)</label>
                <input
                  type="text"
                  value={newTags}
                  onChange={(e) => setNewTags(e.target.value)}
                  placeholder="raft, paxos, 2pc"
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isCreatingDeck || !newTitle.trim()}
                  className="px-5 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold shadow-sm"
                >
                  {isCreatingDeck ? "Creating…" : "Create Deck"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Interactive Reviewer (Leitner Spaced Repetition) */}
      {activeReviewDeck && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setActiveReviewDeck(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-xl w-full p-6 shadow-xl border border-slate-200 flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-bold text-slate-900">{activeReviewDeck.title}</h3>
                <span className="text-xs text-slate-400">
                  Card {currentCardIndex + 1} of {reviewCards.length}
                </span>
              </div>
              <button onClick={() => setActiveReviewDeck(null)} className="text-slate-400 hover:text-slate-700 text-sm">
                ✕
              </button>
            </div>

            <div className="py-6">
              {loadingReview ? (
                <div className="text-center py-12 text-xs text-slate-500">Loading flashcards…</div>
              ) : reviewCards.length === 0 ? (
                <div className="text-center py-12 text-xs text-slate-500">No cards in this deck.</div>
              ) : (
                <div className="space-y-4">
                  {/* Flip Card */}
                  <div
                    onClick={() => setCardFlipped(!cardFlipped)}
                    className="p-8 bg-slate-50 hover:bg-slate-100/80 cursor-pointer rounded-2xl border border-slate-200 min-h-[220px] flex flex-col justify-between transition-all"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="px-2.5 py-0.5 rounded-full bg-teal-50 text-[#0d9488] font-bold border border-teal-200">
                        📦 Box {reviewCards[currentCardIndex]?.box || 1}
                      </span>
                      <span className="text-slate-400 text-[11px]">
                        {cardFlipped ? "Answer Revealed" : "Click to flip"}
                      </span>
                    </div>

                    <div className="my-4 text-center">
                      {!cardFlipped ? (
                        <p className="text-base font-bold text-slate-900">
                          {reviewCards[currentCardIndex]?.front}
                        </p>
                      ) : (
                        <div className="space-y-2">
                          <p className="text-base font-semibold text-emerald-800">
                            {reviewCards[currentCardIndex]?.back}
                          </p>
                          {reviewCards[currentCardIndex]?.explanation && (
                            <p className="text-xs text-slate-500 italic">
                              💡 {reviewCards[currentCardIndex].explanation}
                            </p>
                          )}
                        </div>
                      )}
                    </div>

                    <div className="text-center text-[11px] text-slate-400">
                      {cardFlipped ? "Grade your recall below" : "(Click card to flip)"}
                    </div>
                  </div>

                  {/* Leitner Scoring Actions */}
                  {cardFlipped && (
                    <div className="flex items-center gap-3 pt-2">
                      <button
                        type="button"
                        onClick={() => handleReviewAnswer(false)}
                        className="flex-1 py-2.5 bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 rounded-xl text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
                      >
                        <span>✕</span>
                        <span>Forgot (Reset to Box 1)</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => handleReviewAnswer(true)}
                        className="flex-1 py-2.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 rounded-xl text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
                      >
                        <span>✓</span>
                        <span>Got it (Advance Box)</span>
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Modal: Add Card Manually */}
      {addCardDeckId && (
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
          onClick={() => setAddCardDeckId(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-lg w-full p-6 shadow-xl border border-slate-200"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-base font-bold text-slate-900 mb-4">Add Flashcard</h3>
            <form onSubmit={handleAddCard} className="space-y-4 text-xs">
              <div>
                <label className="block font-semibold text-slate-700 mb-1">Front (Prompt / Question)</label>
                <textarea
                  rows={2}
                  value={cardFront}
                  onChange={(e) => setCardFront(e.target.value)}
                  placeholder="e.g. What is the two-phase commit protocol?"
                  required
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Back (Answer / Definition)</label>
                <textarea
                  rows={3}
                  value={cardBack}
                  onChange={(e) => setCardBack(e.target.value)}
                  placeholder="e.g. A distributed consensus protocol ensuring atomic commits across nodes in prepare and commit phases."
                  required
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">Explanation (Optional)</label>
                <input
                  type="text"
                  value={cardExpl}
                  onChange={(e) => setCardExpl(e.target.value)}
                  placeholder="e.g. Memory hook or further context..."
                  className="w-full px-3.5 py-2 bg-slate-50 border border-slate-200 rounded-xl"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setAddCardDeckId(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSavingCard || !cardFront.trim() || !cardBack.trim()}
                  className="px-5 py-2 bg-[#0d9488] hover:bg-[#0f766e] text-white rounded-xl font-semibold shadow-sm"
                >
                  {isSavingCard ? "Saving…" : "Add Flashcard"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
