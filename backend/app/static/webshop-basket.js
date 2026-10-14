/* The webshop's basket (CR-21, R24, Q23): a JSON object `{variantId: quantity}` in
   localStorage. Nothing leaves the browser until the order is placed; every price
   is computed by the server at "Bestellen" (C5). Loaded once, conditionally, from
   the site shell where the shop module is on. */
(function () {
  "use strict";

  var KEY = "raak_basket";

  function get() {
    try {
      var raw = JSON.parse(window.localStorage.getItem(KEY) || "{}");
      return raw && typeof raw === "object" ? raw : {};
    } catch (_e) {
      return {};
    }
  }

  function set(basket) {
    window.localStorage.setItem(KEY, JSON.stringify(basket));
  }

  function count() {
    var basket = get();
    return Object.keys(basket).reduce(function (n, key) {
      return n + (parseInt(basket[key], 10) || 0);
    }, 0);
  }

  function refresh() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-basket-count]"), function (el) {
      el.textContent = String(count());
    });
  }

  /* The product page's "In mandje": read the chosen tile and the quantity. */
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-add-to-basket]");
    if (!button) return;
    var root = button.closest("[data-shop-buy]");
    if (!root) return;
    var chosen = root.querySelector('input[name="variant_id"]:checked');
    var message = root.querySelector("[data-tiles-message]");
    if (!chosen) {
      if (message) message.hidden = false;
      return;
    }
    if (message) message.hidden = true;
    var quantity = parseInt((root.querySelector('input[name="quantity"]') || {}).value, 10);
    if (!quantity || quantity < 1) quantity = 1;
    var basket = get();
    basket[chosen.value] = (parseInt(basket[chosen.value], 10) || 0) + quantity;
    set(basket);
    refresh();
  });

  /* The "Mandje" link is a form: fill it from localStorage before it posts. */
  document.addEventListener("submit", function (event) {
    var form = event.target.closest("form[data-basket-form]");
    if (!form) return;
    Array.prototype.forEach.call(form.querySelectorAll("[data-basket-row]"), function (row) {
      row.parentNode.removeChild(row);
    });
    var basket = get();
    Object.keys(basket).forEach(function (variantId) {
      var quantity = parseInt(basket[variantId], 10);
      if (!quantity || quantity < 1) return;
      var variant = document.createElement("input");
      variant.type = "hidden";
      variant.name = "variant_id";
      variant.value = variantId;
      variant.setAttribute("data-basket-row", "");
      form.appendChild(variant);
      var amount = document.createElement("input");
      amount.type = "hidden";
      amount.name = "quantity";
      amount.value = String(quantity);
      amount.setAttribute("data-basket-row", "");
      form.appendChild(amount);
    });
  });

  /* The order placed: `#bestel-form`'s good answer (200) empties the basket before
     the browser follows the HX-Redirect, so a buyer who leaves Mollie with the back
     button does not find the same order still in his basket. */
  document.addEventListener("htmx:afterRequest", function (event) {
    var elt = event.detail.elt;
    if (!elt || !elt.matches || !elt.matches("#bestel-form")) return;
    if (event.detail.successful) {
      set({});
      refresh();
    }
  });

  /* "Leeg mandje" on a refused basket: empty it and go back to the shop. */
  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-empty-basket]");
    if (!button) return;
    set({});
    window.location.href = "/webshop";
  });

  refresh();
})();
