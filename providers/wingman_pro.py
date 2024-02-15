import openai
import requests
import azure.cognitiveservices.speech as speechsdk
from api.enums import (
    LogType,
    OpenAiModel,
)
from api.interface import (
    AzureSttConfig,
    SoundConfig,
    WingmanProSettings,
)
from services.printr import Printr


class WingmanPro:
    def __init__(self, wingman_name: str, settings: WingmanProSettings):
        self.wingman_name: str = wingman_name
        self.settings: WingmanProSettings = settings
        self.printr = Printr()

    def transcribe_whisper(self, filename: str):
        with open(filename, "rb") as audio_input:
            files = {"audio_file": (filename, audio_input)}
            response = requests.post(
                url=f"{self.settings.base_url}/transcribe-whisper",
                params={"region": self.settings.region.value},
                files=files,
                timeout=30,
            )
            response.raise_for_status()
            json = response.json()
            transcription = openai.types.audio.Transcription.model_validate(json)
            return transcription

    def transcribe_azure_speech(self, filename: str, config: AzureSttConfig):
        with open(filename, "rb") as audio_input:
            files = {"audio_file": (filename, audio_input)}
            response = requests.post(
                url=f"{self.settings.base_url}/transcribe-azure-speech",
                params={"region": self.settings.region.value},
                json={"languages": config.languages},
                files=files,
                # timeout=30,
            )
        response.raise_for_status()
        json = response.json()
        return json

    def ask(
        self,
        messages: list[dict[str, str]],
        model: OpenAiModel,
        stream: bool = False,
        tools: list[dict[str, any]] = None,
    ):
        serialized_messages = []
        for message in messages:
            if isinstance(message, openai.types.chat.ChatCompletionMessage):
                message_dict = self.__remove_nones(message.dict())
                serialized_messages.append(message_dict)
            else:
                serialized_messages.append(message)

        data = {
            "messages": serialized_messages,
            "model": model.value,
            "stream": stream,
            "tools": tools,
        }
        response = requests.post(
            url=f"{self.settings.base_url}/ask",
            params={"region": self.settings.region.value},
            json=data,
            timeout=10,
        )
        response.raise_for_status()

        json_response = response.json()
        completion = openai.types.chat.ChatCompletion.model_validate(json_response)
        return completion

    def __remove_nones(self, obj):
        """Recursive function to remove None values from a data structure."""
        if isinstance(obj, (list, tuple, set)):
            return type(obj)(self.__remove_nones(x) for x in obj if x is not None)
        elif isinstance(obj, dict):
            return type(obj)(
                (k, self.__remove_nones(v)) for k, v in obj.items() if v is not None
            )
        else:
            return obj

    # def play_audio(
    #     self,
    #     text: str,
    #     api_key: str,
    #     config: AzureTtsConfig,
    #     sound_config: SoundConfig,
    #     audio_player: AudioPlayer,
    #     wingman_name: str,
    # ):
    # speech_config = speechsdk.SpeechConfig(
    #     subscription=api_key,
    #     region=config.region.value,
    # )

    # speech_config.speech_synthesis_voice_name = config.voice

    # speech_synthesizer = speechsdk.SpeechSynthesizer(
    #     speech_config=speech_config,
    #     audio_config=None,
    # )

    # result = speech_synthesizer.speak_text_async(text).get()
    # if result is not None:
    #     audio_player.stream_with_effects(
    #         input_data=result.audio_data,
    #         config=sound_config,
    #         wingman_name=wingman_name,
    #     )

    def get_available_voices(self, locale: str = ""):
        response = requests.get(
            url=f"{self.settings.base_url}/azure-voices",
            params={"region": self.settings.region.value, "locale": locale},
            timeout=10,
        )
        response.raise_for_status()
        voices_dict = response.json()
        voice_infos = [
            {
                "short_name": entry.get("_short_name", ""),
                "name": entry.get("_local_name", ""),
                "locale": entry.get("_locale", ""),
                "gender": self.__resolve_gender(entry.get("_gender")),
            }
            for entry in voices_dict
        ]

        return voice_infos

    def __resolve_gender(self, enum_value: int):
        if enum_value == 1:
            return "Male"
        if enum_value == 2:
            return "Female"
        if enum_value == 3:
            return "Neutral"
        return "Unknown"
