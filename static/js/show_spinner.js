const spinner = document.querySelector(".spinner");
const btns = document.querySelectorAll(".blurApp");
const all = document.querySelectorAll("body > *:not(.spinner)");

console.log(all);

btns.forEach((btn) => {
  btn.addEventListener("click", () => {
    window.scrollTo(0, 0);
    all.forEach((el) => {
      el.classList.add("blur-md");
    });
    spinner.style.display = "flex";
  });
});
