"use client";
import { useEffect, useState } from "react";
import { getProducts, createOrder } from "@/lib/api";
import type { Product } from "@/lib/types";

interface CartItem { product: Product; quantity: number; }

export default function WebshopPage() {
  const [products, setProducts] = useState<Product[]>([]);
  const [cart, setCart] = useState<CartItem[]>([]);
  const [isMember, setIsMember] = useState(false);
  const [form, setForm] = useState({ customer_name: "", customer_email: "", family_id: "" });
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => {
    getProducts().then((r) => setProducts(r.data)).catch(() => {});
  }, []);

  function addToCart(product: Product) {
    setCart((c) => {
      const ex = c.find((i) => i.product.id === product.id);
      if (ex) return c.map((i) => i.product.id === product.id ? { ...i, quantity: i.quantity + 1 } : i);
      return [...c, { product, quantity: 1 }];
    });
  }

  function removeFromCart(productId: number) {
    setCart((c) => c.filter((i) => i.product.id !== productId));
  }

  function getPrice(product: Product) {
    return isMember && product.member_price ? parseFloat(product.member_price) : parseFloat(product.regular_price);
  }

  const total = cart.reduce((sum, item) => sum + getPrice(item.product) * item.quantity, 0);

  // Group products by category
  const categories = [...new Set(products.map((p) => p.category || "Overige"))];

  async function handleOrder(e: React.FormEvent) {
    e.preventDefault();
    if (cart.length === 0) { setError("Je winkelmandje is leeg."); return; }
    setStatus("loading");
    setError("");
    try {
      const res = await createOrder({
        customer_name: form.customer_name,
        customer_email: form.customer_email,
        is_member: isMember,
        family_id: form.family_id ? parseInt(form.family_id) : undefined,
        items: cart.map((i) => ({ product_id: i.product.id, quantity: i.quantity })),
      });
      setConfirmation(res.data.confirmation_number);
      setStatus("success");
      setCart([]);
    } catch {
      setError("Er is iets misgelopen. Probeer opnieuw.");
      setStatus("error");
    }
  }

  if (status === "success") {
    return (
      <div className="max-w-lg mx-auto text-center py-16">
        <div className="text-5xl mb-4">🎉</div>
        <h1 className="text-2xl font-bold text-green-700 mb-2">Bestelling geplaatst!</h1>
        <p className="text-gray-600 mb-1">Bevestigingsnummer: <strong>{confirmation}</strong></p>
        <p className="text-gray-600">Je ontvangt een bevestiging per e-mail.</p>
        <button className="btn-primary mt-6" onClick={() => setStatus("idle")}>Nieuwe bestelling</button>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-blue-800 mb-2">Webshop</h1>
      <p className="text-gray-600 mb-6">Bestel tickets voor Brood en Spelen en andere evenementen.</p>

      <div className="mb-6 flex items-center gap-3">
        <input type="checkbox" id="member" checked={isMember} onChange={(e) => setIsMember(e.target.checked)} className="w-5 h-5" />
        <label htmlFor="member" className="font-medium cursor-pointer">Ik ben lid (ledenkorting van €5 per product)</label>
      </div>

      {categories.map((cat) => (
        <div key={cat} className="mb-8">
          <h2 className="text-xl font-semibold mb-4">{cat}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {products.filter((p) => (p.category || "Overige") === cat).map((product) => (
              <div key={product.id} className="card flex flex-col">
                <h3 className="font-semibold mb-2">{product.name}</h3>
                <div className="text-sm text-gray-600 mb-3">
                  {product.member_price && (
                    <span className="line-through mr-2 text-gray-400">€{parseFloat(product.regular_price).toFixed(2)}</span>
                  )}
                  <span className={`font-bold text-lg ${isMember && product.member_price ? "text-green-700" : "text-gray-900"}`}>
                    €{getPrice(product).toFixed(2)}
                  </span>
                  {isMember && product.member_price && (
                    <span className="ml-2 text-green-700 text-sm">ledenpijs</span>
                  )}
                </div>
                <button className="btn-primary btn-sm mt-auto" onClick={() => addToCart(product)}>
                  Toevoegen
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Cart & checkout */}
      {cart.length > 0 && (
        <div className="card mt-8">
          <h2 className="text-xl font-bold mb-4">Winkelmandje</h2>
          <div className="space-y-2 mb-4">
            {cart.map((item) => (
              <div key={item.product.id} className="flex items-center justify-between">
                <span>{item.quantity}× {item.product.name}</span>
                <div className="flex items-center gap-3">
                  <span className="font-medium">€{(getPrice(item.product) * item.quantity).toFixed(2)}</span>
                  <button onClick={() => removeFromCart(item.product.id)} className="text-red-600 text-sm hover:underline">
                    ✕
                  </button>
                </div>
              </div>
            ))}
            <div className="border-t pt-2 flex justify-between font-bold text-lg">
              <span>Totaal</span>
              <span>€{total.toFixed(2)}</span>
            </div>
          </div>

          <form onSubmit={handleOrder} className="space-y-4 border-t pt-4">
            <h3 className="font-semibold">Contactgegevens</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="label">Naam *</label>
                <input className="input" required value={form.customer_name} onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))} />
              </div>
              <div>
                <label className="label">E-mailadres *</label>
                <input type="email" className="input" required value={form.customer_email} onChange={(e) => setForm((f) => ({ ...f, customer_email: e.target.value }))} />
              </div>
            </div>
            {isMember && (
              <div>
                <label className="label">Gezinsnummer</label>
                <input type="number" className="input" placeholder="Optioneel" value={form.family_id} onChange={(e) => setForm((f) => ({ ...f, family_id: e.target.value }))} />
              </div>
            )}
            {error && <p className="text-red-600 text-sm">{error}</p>}
            <button type="submit" disabled={status === "loading"} className="btn-primary w-full sm:w-auto">
              {status === "loading" ? "Bezig…" : `Bestelling plaatsen (€${total.toFixed(2)})`}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
