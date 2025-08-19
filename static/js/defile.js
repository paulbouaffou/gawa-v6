class Words {

	constructor(words) {
		this.app = document.getElementById('app');
		this.words = words
		this.wordIndex = 0

		this.action()
	}

	async action () {
		await this.cleanWord()
		await this.sleep(500)
		await this.generateWord()
	}

	sleep (ms) {
		return new Promise(resolve => setTimeout(resolve, ms))
	}

	async cleanWord () {
		await new Promise(async resolve => {
			while (this.app.textContent !== '') {
				this.app.textContent = this.app.textContent.slice(0, -1);
				await this.sleep(100)
			}
			resolve()
		})
	}

	async generateWord () {
		await new Promise(async resolve => {
			const word = this.words[this.wordIndex];
			let letterPosition = 0;
			while (word.length !== letterPosition) {
				this.app.textContent += word[letterPosition].toLowerCase();
				await this.sleep(150);
				letterPosition = letterPosition + 1
			}
			resolve()
		});
		await this.sleep(2000);
		if (this.wordIndex + 1 === this.words.length) {
			this.wordIndex = 0
		} else {
			this.wordIndex = this.wordIndex + 1;
		}
		this.action()
	}
}

new Words(["orphelins", "à wikifier", "à sourcer", "à vérifier l'admissibilité", "très courts et oubliés", "non neutres", "à problèmes multiples", "promotionnels", "à style non encyclopédique"]);