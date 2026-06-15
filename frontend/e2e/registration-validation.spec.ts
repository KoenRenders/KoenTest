import { test, expect } from "@playwright/test";

// #160 — clientside validatie: zonder een geldig gekozen postcode (enkel typen
// telt niet) wordt de gezinsregistratie geblokkeerd met een duidelijke melding.
test("gezinsregistratie zonder geldige postcode wordt geblokkeerd", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Word lid" }).click();

  await page.getByTestId("person-first-name").fill("Test");
  await page.getByTestId("person-last-name").fill("Gezin");
  await page.getByTestId("person-email").fill("nopc@example.com");
  await page.getByTestId("person-mobile").fill("0470000000");
  await page.getByTestId("address-street").fill("Teststraat");
  await page.getByTestId("address-house-number").fill("1");

  // Wel typen, maar GEEN suggestie aanklikken → postal_code blijft leeg.
  await page.getByTestId("postal-input").fill("2400");

  await page.getByTestId("payment-transfer").check();
  await page.getByTestId("family-submit").click();

  await expect(page.getByText("Selecteer een geldige postcode")).toBeVisible();
});
