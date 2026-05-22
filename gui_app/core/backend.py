from search_functions import (
    ensure_red_book_index,
    ensure_sentence_index,
    is_red_book_index_valid,
    is_sentence_index_valid,
    load_config,
    search_for_word_data,
)


class GuiBackend:
    def __init__(
        self,
        *,
        load_config_func=load_config,
        ensure_sentence_index_func=ensure_sentence_index,
        ensure_red_book_index_func=ensure_red_book_index,
        is_sentence_index_valid_func=is_sentence_index_valid,
        is_red_book_index_valid_func=is_red_book_index_valid,
        search_for_word_data_func=search_for_word_data,
    ):
        self._load_config = load_config_func
        self._ensure_sentence_index = ensure_sentence_index_func
        self._ensure_red_book_index = ensure_red_book_index_func
        self._is_sentence_index_valid = is_sentence_index_valid_func
        self._is_red_book_index_valid = is_red_book_index_valid_func
        self._search_for_word_data = search_for_word_data_func

    def load_config(self):
        return self._load_config()

    def indexes_are_ready(self):
        return (
            self._is_sentence_index_valid()
            and self._is_red_book_index_valid()
        )

    def build_indexes(self, progress_callback):
        sentence_status = self._ensure_sentence_index(
            progress_callback=progress_callback
        )
        red_book_status = self._ensure_red_book_index(
            progress_callback=progress_callback
        )
        return {
            "sentence_index": sentence_status,
            "red_book_index": red_book_status,
        }

    def search(self, query, sentence_limit):
        return self._search_for_word_data(query, sentence_limit=sentence_limit)
