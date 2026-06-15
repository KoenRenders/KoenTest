import { test, expect } from "@playwright/test";

// Kernflow (#128): gezinsregistratie via "Word lid" met betaaltype overschrijving.
// Die raakt Mollie niet → stabiel zonder gateway-stub. Vereist een backend met
// geseede postcodes (zie e2e/README.md).
test("gezinsregistratie via Word lid met overschrijving", async ({ page }) => {
  await page.goto("/");

  // Open het "Lid worden"-formulier.
  await page.getByRole("button", { name: "Word lid" }).click();

  // Hoofdgezinslid (e-mail + mobiel zijn verplicht).
  const uniek = Date.now();
  await page.getByTestId("person-first-name").fill("Test");
  await page.getByTestId("person-last-name").fill("Gezin");
  await page.getByTestId("person-email").fill(`e2e+${uniek}@example.com`);
  await page.getByTestId("person-mobile").fill("0470000000");

  // Adres.
  await page.getByTestId("address-street").fill("Teststraat");
  await page.getByTestId("address-house-number").fill("1");

  // Postcode: typen en de eerste suggestie kiezen (autocomplete-dropdown).
  await page.getByTestId("postal-input").fill("2400");
  await page.getByTestId("postal-option").first().click();

  // Betaaltype overschrijving (geen Mollie-redirect).
  await page.getByTestId("payment-transfer").check();

  // Verzenden.
  await page.getByTestId("family-submit").click();

  // Bevestiging.
  await expect(page.getByTestId("registration-success")).toBeVisible();
});
