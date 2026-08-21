import { expect, test } from "@playwright/test";

test("landing and map remain scientifically honest", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Inteligencia satelital para anticiparnos al fuego." })).toBeVisible();
  await page.getByRole("link", { name: "Explorar VIGÍA" }).click();
  await expect(page).toHaveURL(/\/mapa$/);
  await expect(page.getByText("Sin incidentes verificados")).toBeVisible();
  await expect(page.getByText("99,9% de precisión")).toHaveCount(0);
});

test("replay separates historical knowledge from later truth", async ({ page }) => {
  await page.goto("/replay");
  await expect(page.getByText("REPLAY HISTÓRICO · NO ES MONITORIZACIÓN LIVE")).toBeVisible();
  await expect(page.getByRole("heading", { name: "LO QUE VIGÍA SABÍA" })).toBeVisible();
  const comparison = page.getByRole("checkbox", {
    name: "Activar comparación posterior con referencia oficial",
  });
  await expect(comparison).not.toBeChecked();
  await expect(page.getByRole("heading", { name: "LO QUE SABEMOS AHORA" })).toHaveCount(0);
  await expect(page.getByText(/Ningún color es el único indicador/)).toBeVisible();
});

test("validation exposes evidence and unavailable results honestly", async ({ page }) => {
  await page.goto("/validacion");
  await expect(page.getByText("VALIDACIÓN EXPERIMENTAL · NO ES UN CLAIM OPERACIONAL")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Si no podemos defender la métrica, no la mostramos." })).toBeVisible();
  await expect(page.getByText("Los controles no se inventan")).toBeVisible();
  await expect(page.getByText("99,9% de precisión")).toHaveCount(0);
});
