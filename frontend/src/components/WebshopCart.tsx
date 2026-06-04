"use client";
import { useState } from "react";
import { createOrder } from "@/lib/api";
import type { CartItem } from "@/lib/types";

interface Props {
  cart: CartItem[];
  setCart: React.Dispatch<React.SetStateAction<CartItem[]>>;
  onClose: () => void;
}

export default function WebshopCart({ cart, setCart, onClose }: Props) {
  const [isMember, setIsMember] = useState(false);
  const [familyId, setFamilyId] = useState("");
  const [form, setForm] = useState({ customer_name: "", customer_email: "" });
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState("");

  const getPrice = (item: CartItem) => {
    return isMember && item.product.member_price
      ? parseFloat(item.product.member_price)
      : parseFloat(item.product.regular_price);
  };

  const total = cart.reduce((s, item) => s + getPrice(item) * item.quantity, 0);

  const updateQty = (productId: number, delta: number) => {
    setCart((prev) =>
      prev
        .map((i) => (i.product.id === productId ? { ...i, quantity: i.quantity + delta } : i))
        .filter((i) => i.quantity > 0)
    );
  };

  const handleOrder = async (e: React.FormEvent) => {
    e.preventDefault();
    if (cart.length === 0) {
      setError("Je winkelmandje is leeg.");
      return;
    }
    setStatus("loading");
    setError("");
    try {
      const res = await createOrder({
        customer_name: form.customer_name,
        customer_email: form.customer_email,
        is_member: isMember,
        family_id: familyId ? parseInt(familyId) : undefined,
        items: cart.map((i) => ({ product_id: i.product.id, quantity: i.quantity })),
      });
      setConfirmation(res.data.confirmation_number);
      setStatus("success");
      setCart([]);
    } catch {
      setError("Er is iets misgelopen. Probeer opnieuw.");
      setStatus("error");
    } finally {
      if (status !== "success") setStatus("idle");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-end sm:items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-bold">Winkelwagen</h2>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-2xl leading-none">&times;</button>
          </div>

          {status === "success" ? (
            <div className="text-center py-8">
              <p className="text-4xl mb-3">&#x1F389;</p>
              <h3 className="text-xl font-bold text-green-700 mb-2">Bestelling geplaatst!</h3>
              <p className="text-gray-600 mb-1">
                Bevestigingsnummer: <strong className="font-mono">{confirmation}</strong>
              </p>
              <p className="text-gray-500 text-sm">Je ontvangt een bevestiging per e-mail.</p>
              <button onClick={onClose} className="btn-primary mt-6">Sluiten</button>
            </div>
          ) : (
            <>
              {/* Cart items */}
              {cart.length === 0 ? (
                <p className="text-gray-400 text-center py-8">Je winkelwagen is leeg.</p>
              ) : (
                <div className="space-y-3 mb-4">
                  {cart.map((item) => (
                    <div key={item.product.id} className="flex items-center gap-3">
                      <div className="flex-1">
                        <p className="font-medium text-sm">{item.product.name}</p>
                        <p className="text-sm text-gray-500">
                          &euro;{getPrice(item).toFixed(2)} p.st.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => updateQty(item.product.id, -1)}
                          className="w-7 h-7 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100 flex items-center justify-center text-sm"
                        >
                          -
                        </button>
                        <span className="w-6 text-center font-medium">{item.quantity}</span>
                        <button
                          onClick={() => updateQty(item.product.id, 1)}
                          className="w-7 h-7 rounded-full border border-gray-300 text-gray-600 hover:bg-gray-100 flex items-center justify-center text-sm"
                        >
                          +
                        </button>
                      </div>
                      <span className="text-sm font-semibold w-16 text-right">
                        &euro;{(getPrice(item) * item.quantity).toFixed(2)}
                      </span>
                    </div>
                  ))}
                  <div className="border-t pt-2 flex justify-between font-bold">
                    <span>Totaal</span>
                    <span>&euro;{total.toFixed(2)}</span>
                  </div>
                </div>
              )}

              {/* Checkout form */}
              <form onSubmit={handleOrder} className="space-y-4 border-t pt-4">
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="is_member"
                    checked={isMember}
                    onChange={(e) => setIsMember(e.target.checked)}
                    className="w-4 h-4"
                  />
                  <label htmlFor="is_member" className="text-sm font-medium cursor-pointer">
                    Ik ben lid (ledenkorting)
                  </label>
                </div>

                {isMember && (
                  <div>
                    <label className="label">Gezinsnummer</label>
                    <input
                      type="number"
                      className="input"
                      placeholder="Optioneel"
                      value={familyId}
                      onChange={(e) => setFamilyId(e.target.value)}
                    />
                  </div>
                )}

                <div>
                  <label className="label">Naam *</label>
                  <input
                    className="input"
                    required
                    value={form.customer_name}
                    onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))}
                  />
                </div>
                <div>
                  <label className="label">E-mailadres *</label>
                  <input
                    type="email"
                    className="input"
                    required
                    value={form.customer_email}
                    onChange={(e) => setForm((f) => ({ ...f, customer_email: e.target.value }))}
                  />
                </div>

                {error && <p className="text-red-600 text-sm">{error}</p>}

                <button
                  type="submit"
                  disabled={status === "loading" || cart.length === 0}
                  className="btn-primary w-full"
                >
                  {status === "loading" ? "Bezig..." : `Bestelling plaatsen (€${total.toFixed(2)})`}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
