import assert from "node:assert/strict";
import { describe, test } from "node:test";

import { baseState, flush, mount } from "./harness.mjs";

const iso = (day) => day.toISOString().slice(0, 10);

function weekAround(offsetWeeks) {
  const today = new Date();
  const monday = new Date(
    Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()),
  );
  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7));
  monday.setUTCDate(monday.getUTCDate() + offsetWeeks * 7);
  const dates = {};
  for (let day = 1; day <= 6; day += 1) {
    const current = new Date(monday);
    current.setUTCDate(current.getUTCDate() + day - 1);
    dates[String(day)] = iso(current);
  }
  const end = new Date(monday);
  end.setUTCDate(end.getUTCDate() + 5);
  return { start: iso(monday), end: iso(end), dates };
}

function stateAroundToday() {
  const state = baseState();
  const weeks = [-1, 0, 1].map((offset, index) => {
    const week = weekAround(offset);
    return {
      index: index + 1,
      start: week.start,
      end: week.end,
      label: `Semaine ${index + 1}`,
      range: `${week.start} - ${week.end}`,
      dates: week.dates,
    };
  });
  state.meta.semester = {
    dateDebut: weeks[0].start,
    dateFin: weeks[2].end,
    weeks,
  };
  state.occurrences = weeks.map((week) => ({
    date: week.dates["1"],
    jour: "1",
    blockId: "LOG430-02:0",
    courseId: "LOG430-02",
    sigle: "LOG430",
    groupe: "02",
    titre: "Architecture logicielle",
    room: "A-1502",
    kind: "cours",
    heureDebut: "09:00",
    heureFin: "12:00",
    overridden: false,
    canceled: false,
  }));
  return state;
}

describe("week navigation", () => {
  test("offers one entry per week of the session", async () => {
    const app = await mount();
    assert.deepEqual(
      app.queryAll("#weekSelect fluent-option").map((option) => option.textContent),
      [
        "S1 (5 janv. - 10 janv.)",
        "S2 (12 janv. - 17 janv.)",
        "S3 (19 janv. - 24 janv.)",
      ],
    );
    assert.equal(app.byId("weekPicker").hidden, false);
    app.close();
  });

  test("starts on the first week when today is outside the session", async () => {
    const app = await mount();
    assert.equal(app.byId("weekSelect").value, "1");
    assert.equal(app.byId("weekPrev").disabled, true);
    assert.equal(app.byId("weekNext").disabled, false);
    app.close();
  });

  test("walks forward and back with the arrows", async () => {
    const app = await mount();

    app.byId("weekNext").click();
    await flush();
    assert.equal(app.text(".dayhead__date"), "12 janv.");

    app.byId("weekPrev").click();
    await flush();
    assert.equal(app.text(".dayhead__date"), "5 janv.");
    app.close();
  });

  test("stops at the last week", async () => {
    const app = await mount();

    app.byId("weekNext").click();
    app.byId("weekNext").click();
    await flush();

    assert.equal(app.byId("weekNext").disabled, true);
    assert.equal(app.byId("weekPrev").disabled, false);
    app.close();
  });

  test("jumps to the week picked in the dropdown", async () => {
    const app = await mount();

    app.select(app.byId("weekSelect"), "3");
    await flush();

    assert.equal(app.text(".dayhead__date"), "19 janv.");
    app.close();
  });

  test("changing week does not ask the server again", async () => {
    const app = await mount();
    app.byId("weekNext").click();
    await flush();

    assert.equal(app.server.calls.length, 1);
    app.close();
  });

  test("moves with the left and right arrow keys", async () => {
    const app = await mount();

    app.key("ArrowRight");
    await flush();
    assert.equal(app.byId("weekSelect").value, "2");

    app.key("ArrowLeft");
    await flush();
    assert.equal(app.byId("weekSelect").value, "1");
    app.close();
  });

  test("ignores the arrow keys while typing", async () => {
    const app = await mount();
    const input = app.byId("fStart");
    input.focus();
    assert.equal(app.window.document.activeElement, input);

    app.key("ArrowRight");
    await flush();

    assert.equal(app.byId("weekSelect").value, "1");
    app.close();
  });

  test("offers a shortcut back to the current week", async () => {
    const app = await mount({ state: stateAroundToday() });
    assert.equal(app.byId("weekSelect").value, "2");
    assert.equal(app.byId("weekToday").hidden, true);

    app.byId("weekPrev").click();
    await flush();
    assert.equal(app.byId("weekToday").hidden, false);

    app.byId("weekToday").click();
    await flush();
    assert.equal(app.byId("weekSelect").value, "2");
    app.close();
  });

  test("hides the week picker when the session has no calendar", async () => {
    const state = baseState();
    state.meta.semester = null;
    const app = await mount({ state });

    assert.equal(app.byId("weekPicker").hidden, true);
    assert.equal(app.byId("scopeOccurrence").disabled, true);
    assert.equal(app.blocks().length, 0);
    app.close();
  });
});

describe("session switching", () => {
  test("loads the session picked in the dropdown", async () => {
    const app = await mount();

    app.select(app.byId("sessionSelect"), "H2025");
    await flush();

    assert.equal(app.server.lastCall("/state").query, "session=H2025&lang=fr");
    app.close();
  });

  test("keeps showing the session the server answers with", async () => {
    const app = await mount();
    const other = baseState();
    other.session = "H2025";
    app.server.reply("/state", other);

    app.select(app.byId("sessionSelect"), "H2025");
    await flush();

    assert.equal(app.byId("sessionSelect").value, "H2025");
    app.close();
  });
});

describe("edit scope", () => {
  test("starts on the whole series", async () => {
    const app = await mount();
    assert.equal(app.byId("scopeToggle").activeid, "scopeSeries");
    assert.equal(app.byId("board").classList.contains("is-occurrence"), false);
    app.close();
  });

  test("switches to the single séance scope", async () => {
    const app = await mount();

    app.fire(app.byId("scopeToggle"), "change", {
      detail: app.byId("scopeOccurrence"),
    });
    await flush();

    assert.ok(app.byId("board").classList.contains("is-occurrence"));
    app.close();
  });

  test("renames the delete button in the séance scope", async () => {
    const app = await mount();
    assert.equal(
      app.blockFor("LOG430-02:0").querySelector(".block__del").title,
      "Supprimer le cours",
    );

    app.fire(app.byId("scopeToggle"), "change", {
      detail: app.byId("scopeOccurrence"),
    });
    await flush();

    assert.equal(
      app.blockFor("LOG430-02:0").querySelector(".block__del").title,
      "Annuler cette séance",
    );
    app.close();
  });

  test("only offers to restore a séance in the séance scope", async () => {
    const app = await mount();
    app.byId("weekNext").click();
    await flush();
    assert.equal(app.blockFor("LOG430-02:0").querySelector(".block__reset"), null);

    app.fire(app.byId("scopeToggle"), "change", {
      detail: app.byId("scopeOccurrence"),
    });
    await flush();

    assert.ok(app.blockFor("LOG430-02:0").querySelector(".block__reset"));
    app.close();
  });

  test("ignores an unknown scope", async () => {
    const app = await mount();

    app.fire(app.byId("scopeToggle"), "change", { detail: null });
    await flush();

    assert.equal(app.byId("board").classList.contains("is-occurrence"), false);
    app.close();
  });
});
