const showBtn2 = 100

let toTopFunction = function toTopFunc() {
  const toTopBtn = document.getElementById('to-top')
  const toBottomBtn = document.getElementById('to-bottom')

  toTopBtn.addEventListener('click', () => {
    window.scrollTo(0, 0)
  })

  function onScrollFunction() {
    if (
      document.body.scrollTop > showBtn2 ||
      document.documentElement.scrollTop > showBtn2
    ) {
      toTopBtn.style.display = 'block';
      console.log("to up");
    } else {
      toTopBtn.style.display = 'none'
    }
  }

  window.addEventListener('scroll', onScrollFunction)
}

window.onload = toTopFunction
