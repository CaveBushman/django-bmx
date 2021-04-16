const spinner = document.querySelector('.spinner')
const btns = document.querySelectorAll('.blur')
const all = document.querySelectorAll('body > *:not(.spinner)')

console.log(btns);

btns.forEach(btn => {
  btn.addEventListener('click', () => {
    all.forEach((el) => (el.style.filter = `blur(8px)`))
    spinner.style.display = 'flex'
  })
})

