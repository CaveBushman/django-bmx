const spinner = document.querySelector('.spinner')
const btn = document.getElementById('blur')
const all = document.querySelectorAll('body > *:not(.spinner)')

console.log(all);
btn.addEventListener('click', () => {
    all.forEach((el) => (el.style.filter = `blur(8px)`))
    spinner.style.display = 'flex'
  })