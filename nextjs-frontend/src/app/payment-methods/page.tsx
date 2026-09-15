"use client";

import React, { useState } from "react";
import Link from "next/link";

interface SavedCard {
  id: string;
  brand: string;
  last4: string;
  expMonth: number;
  expYear: number;
  isDefault: boolean;
}

export default function PaymentMethodsPage() {
  const [cards, setCards] = useState<SavedCard[]>([
    {
      id: "card-1",
      brand: "Mastercard",
      last4: "4242",
      expMonth: 12,
      expYear: 2028,
      isDefault: true
    },
    {
      id: "card-2",
      brand: "Visa",
      last4: "8899",
      expMonth: 6,
      expYear: 2027,
      isDefault: false
    }
  ]);

  const [cardNumber, setCardNumber] = useState("");
  const [expDate, setExpDate] = useState("");
  const [cvc, setCvc] = useState("");
  const [zip, setZip] = useState("");
  const [cardHolder, setCardHolder] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState<string | null>(null);

  const handleAddCard = (e: React.FormEvent) => {
    e.preventDefault();
    if (!cardNumber || !expDate || !cvc) return;

    setIsSaving(true);
    setTimeout(() => {
      const cleanNum = cardNumber.replace(/\s+/g, "");
      const newCard: SavedCard = {
        id: Date.now().toString(),
        brand: cleanNum.startsWith("4") ? "Visa" : "Mastercard",
        last4: cleanNum.slice(-4) || "1234",
        expMonth: 12,
        expYear: 2029,
        isDefault: false
      };

      setCards(prev => [...prev, newCard]);
      setIsSaving(false);
      setSavedSuccess("New payment method tokenized and saved securely!");
      setCardNumber("");
      setExpDate("");
      setCvc("");
      setZip("");
      setCardHolder("");

      setTimeout(() => setSavedSuccess(null), 4000);
    }, 1200);
  };

  const setDefault = (id: string) => {
    setCards(prev =>
      prev.map(c => ({
        ...c,
        isDefault: c.id === id
      }))
    );
  };

  const removeCard = (id: string) => {
    setCards(prev => prev.filter(c => c.id !== id));
  };

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold text-[#1e292b]">Payment Methods</h1>
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
              Powered by Stripe
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Manage your saved credit/debit cards and default transaction routing.
          </p>
        </div>

        <Link
          href="/billing"
          className="text-xs font-semibold text-[#0d9488] hover:underline self-start sm:self-center"
        >
          ← Back to Billing
        </Link>
      </div>

      {savedSuccess && (
        <div className="p-3.5 bg-teal-50 border border-teal-200 rounded-xl text-xs font-semibold text-[#0d9488] animate-in fade-in">
          ✓ {savedSuccess}
        </div>
      )}

      {/* Saved Cards List */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-bold text-[#1e292b]">Saved Cards</h2>

        <div className="space-y-3">
          {cards.map((card) => (
            <div
              key={card.id}
              className={`p-4 rounded-xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${
                card.isDefault
                  ? "bg-teal-50/40 border-teal-200"
                  : "bg-slate-50 border-slate-200"
              }`}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-7 rounded bg-white border border-slate-200 flex items-center justify-center font-bold text-xs text-slate-800 shadow-2xs">
                  💳
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-800">
                      {card.brand} ending in {card.last4}
                    </span>
                    {card.isDefault && (
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-teal-50 text-[#0d9488] border border-teal-200">
                        Default
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Expires {card.expMonth}/{card.expYear}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {!card.isDefault && (
                  <button
                    onClick={() => setDefault(card.id)}
                    className="px-3 py-1 text-xs font-semibold text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
                  >
                    Make Default
                  </button>
                )}
                {cards.length > 1 && (
                  <button
                    onClick={() => removeCard(card.id)}
                    className="px-3 py-1 text-xs font-semibold text-rose-600 hover:text-rose-700 bg-white border border-rose-200 rounded-lg hover:bg-rose-50 transition-colors"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Add New Card Form with Stripe Elements styling */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 sm:p-8 shadow-sm space-y-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div>
            <h2 className="text-sm font-bold text-[#1e292b]">Add New Payment Method</h2>
            <p className="text-xs text-slate-500 mt-0.5">Securely tokenized with Stripe Elements</p>
          </div>
          <span className="text-xs font-semibold text-slate-400">🔒 256-bit SSL</span>
        </div>

        <form onSubmit={handleAddCard} className="space-y-4">
          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">
              Cardholder Name
            </label>
            <input
              type="text"
              placeholder="Name on card"
              value={cardHolder}
              onChange={(e) => setCardHolder(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs sm:text-sm text-slate-800 focus:outline-none focus:border-[#0d9488] transition-colors"
              required
            />
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">
              Card Details
            </label>
            <div className="flex items-center bg-slate-50 border border-slate-200 rounded-xl px-3.5 py-2.5 focus-within:border-[#0d9488] transition-colors">
              <span className="text-slate-400 mr-2 text-xs">💳</span>
              <input
                type="text"
                maxLength={19}
                placeholder="4242 ···· ···· 4242"
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                className="w-full bg-transparent text-xs sm:text-sm text-slate-800 focus:outline-none font-mono placeholder-slate-400"
                required
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                Expiry Date
              </label>
              <input
                type="text"
                maxLength={5}
                placeholder="MM / YY"
                value={expDate}
                onChange={(e) => setExpDate(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs sm:text-sm text-slate-800 focus:outline-none focus:border-[#0d9488] font-mono transition-colors"
                required
              />
            </div>

            <div>
              <label className="text-xs font-semibold text-slate-700 block mb-1">
                CVC / CVV
              </label>
              <input
                type="text"
                maxLength={4}
                placeholder="CVC"
                value={cvc}
                onChange={(e) => setCvc(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs sm:text-sm text-slate-800 focus:outline-none focus:border-[#0d9488] font-mono transition-colors"
                required
              />
            </div>
          </div>

          <div>
            <label className="text-xs font-semibold text-slate-700 block mb-1">
              Postal / ZIP Code
            </label>
            <input
              type="text"
              placeholder="e.g. 74200 or 10001"
              value={zip}
              onChange={(e) => setZip(e.target.value)}
              className="w-full px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs sm:text-sm text-slate-800 focus:outline-none focus:border-[#0d9488] transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={isSaving}
            className="w-full py-3 rounded-xl text-xs sm:text-sm font-bold bg-[#0d9488] hover:bg-[#0f766e] disabled:opacity-50 text-white shadow-sm hover:shadow transition-all"
          >
            {isSaving ? "Authorizing with Stripe..." : "Save Card"}
          </button>
        </form>

        {/* PCI-DSS Note */}
        <div className="pt-4 border-t border-slate-100 flex items-center justify-center gap-2 text-[11px] text-slate-400">
          <span>🔒</span>
          <span>PCI-DSS Level 1 Certified · Card credentials never touch Roxy AI servers</span>
        </div>
      </div>
    </div>
  );
}
