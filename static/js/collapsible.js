const collapsibles = [...document.querySelectorAll("[data-collapsible-main]")];

collapsibles.forEach((collapsible) => {
  const head = collapsible.querySelector("[data-collapsible-head]");
  head.addEventListener("click", () => {
    collapsibles
      .filter((c) => c !== collapsible)
      .forEach((c) => c.classList.remove("collapsible-active"));
    collapsible.classList.toggle("collapsible-active");
  });
});

console.log("Script collapsibles nahrán");
