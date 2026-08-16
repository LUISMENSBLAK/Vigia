import { expect, test } from "@playwright/test";

test("landing and map remain scientifically honest", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inteligencia satelital para anticiparnos al fuego." })).toBeVisible();
  await page.getByRole("link", { name: "Explorar VIGÍA" }).click();
  await expect(page).toHaveURL(/\/mapa$/);
  await expect(page.getByText("Sin incidentes verificados")).toBeVisible();
  await expect(page.getByText("99,9% de precisión")).toHaveCount(0);
});
