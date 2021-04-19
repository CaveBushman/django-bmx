const myfunction = function myFunc() {

    const inputs = document.querySelectorAll(
      '.uciid-container .inputs-container input'
    )

    inputs[0].focus()

    inputs.forEach((input, index) => {
      input.addEventListener('keydown', (e) => {
        if (e.key >= 0 && e.key <= 9 && index < inputs.length) {
          inputs[index].value = ''
          if (index === inputs.length - 1) setTimeout(() => input.blur(), 9)
          else setTimeout(() => inputs[index + 1].focus(), 9)
        } else if (e.key === 'Backspace' && index > 0) {
          setTimeout(() => inputs[index - 1].focus(), 9)
          inputs[index - 1].value = ''
        }
      })

      input.addEventListener('paste', (e) => {
        input.value = ''
        let paste = (e.clipboardData || window.clipboardData)
          .getData('text')
          .split('')
        setTimeout(() => {
          inputs.forEach((input1, index) => {
            input1.value = ''
            input1.value = paste[index]
          })
        }, 10)
      })
    })
  }

  window.onload = myfunction
