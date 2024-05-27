import random
import string
import asyncio
import threading
import time
import json
from typing import (
    TYPE_CHECKING,
    Mapping,
)
from api.interface import (
    SettingsConfig,
    SkillConfig,
    WingmanConfig,
    WingmanInitializationError,
)
from api.enums import (
    LogSource,
    LogType,
)
from skills.skill_base import Skill
from services.printr import Printr

if TYPE_CHECKING:
    from wingmen.wingman import Wingman

printr = Printr()

class Timer(Skill):

    def __init__(
        self,
        config: SkillConfig,
        wingman_config: WingmanConfig,
        settings: SettingsConfig,
        wingman: "Wingman",
    ) -> None:

        self.timers = {}
        self.wingman = wingman
        self.available_tools = []

        super().__init__(
            config=config, wingman_config=wingman_config, settings=settings, wingman=wingman
        )

    async def validate(self) -> list[WingmanInitializationError]:
        errors = await super().validate()
        return errors
    
    def get_tools(self) -> list[tuple[str, dict]]:
        tools = [
            (
                "set_timer",
                {
                    "type": "function",
                    "function": {
                        "name": "set_timer",
                        "description": "set_timer function to delay other available functions.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "delay": {
                                    "type": "number",
                                    "description": "The delay/timer in seconds.",
                                },
                                "function": {
                                    "type": "string",
                                    # "enum": self._get_available_tools(), # end up beeing a recursive nightmare
                                    "description": "The name of the function to execute after the delay. Must be a function name from the available tools.",
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "The parameters for the function to execute after the delay. Must be a valid object with the required properties to their values. Can not be empty.",
                                },
                            },
                            "required": ["detlay", "function", "parameters"],
                        },
                    },
                }
            ),
            (
                "get_timer_status",
                {
                    "type": "function",
                    "function": {
                        "name": "get_timer_status",
                        "description": "Get a list of all running timers and their remaining time and id.",
                    },
                }
            ),
            (
                "cancel_timer",
                {
                    "type": "function",
                    "function": {
                        "name": "cancel_timer",
                        "description": "Cancel a running timer by its id.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "id": {
                                    "type": "string",
                                    "description": "The id of the timer to cancel.",
                                },
                            },
                            "required": ["id"],
                        },
                    },
                }
            ),
            (
                "remind_me",
                {
                    "type": "function",
                    "function": {
                        "name": "remind_me",
                        "description": "Must only be called with the set_timer function. Will remind the user with the given message.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "The message to say to the user. Must be given as a string.",
                                },
                            },
                            "required": ["message"],
                        },
                    },
                }
            ),

        ]
        return tools

    def _get_available_tools(self) -> list[dict[str, any]]:
        tools = self.wingman.build_tools()
        tool_names = []
        for tool in tools:
            name = tool.get("function", {}).get("name", None)
            if name:
                tool_names.append(name)

        print(f"Available tools: {tool_names}")
        return tool_names

    async def execute_tool(
        self, tool_name: str, parameters: dict[str, any]
    ) -> tuple[str, str]:
        function_response = ""
        instant_response = ""

        if tool_name in ["set_timer", "get_timer_status", "cancel_timer", "remind_me"]:
            if self.settings.debug_mode:
                self.start_execution_benchmark()

            if tool_name == "set_timer":
                function_response = await self.set_timer(
                    delay=parameters.get("delay", None),
                    function=parameters.get("function", None),
                    parameters=parameters.get("parameters", {}),
                )
            elif tool_name == "get_timer_status":
                function_response = await self.get_timer_status()
            elif tool_name == "cancel_timer":
                function_response = await self.cancel_timer(timer_id=parameters.get("id", None))
            elif tool_name == "remind_me":
                function_response = await self.reminder(message=parameters.get("message", None))

            if self.settings.debug_mode:
                await self.print_execution_time()

            print(function_response)

        return function_response, instant_response
    
    async def _get_tool_parameter_type_by_name(self, type_name: str) -> any:
        if type_name == "object":
            return dict
        elif type_name == "string":
            return str
        elif type_name == "number":
            return int
        elif type_name == "boolean":
            return bool
        elif type_name == "array":
            return list
        else:
            return None
        
    async def set_timer(self, delay: int = None, function: str = None, parameters: dict[str, any] = None) -> str:
        check_counter = 0
        max_checks = 2
        errors = []

        while (check_counter == 0 or errors) and check_counter < max_checks:
            print(f"Trying to set timer with delay {delay} for function {function} with parameters {parameters}. Try {check_counter + 1}/{max_checks}.")
            errors = []
        
            if delay is None or function is None:
                errors.append("Missing delay or function.")
            elif delay < 0:
                errors.append("No timer set, delay must be greater than 0.")

            if "." in function:
                function = function.split(".")[1]

            # check if tool call exists
            tool_call = None
            tool_call = next(
                (tool for tool in self.wingman.build_tools() if tool.get("function", {}).get("name", False) == function),
                None
            )

            # if not valid it might be a command
            if not tool_call and self.wingman.get_command(function):
                parameters = {"command_name": function}
                function = "execute_command"

            if not tool_call:
                errors.append(f"Function {function} does not exist.")
            else:
                print(f"tool call: {tool_call}")
                if tool_call.get("function", False) and tool_call.get("function", {}).get("parameters", False):
                    properties =  tool_call.get("function", {}).get("parameters", {}).get("properties", {})
                    print(f"properties: {properties}")
                    required_parameters = tool_call.get("function", {}).get("parameters", {}).get("required", [])
                    print(f"required_parameters: {required_parameters}")

                    for name, value in properties.items():
                        if name in parameters:
                            real_type = await self._get_tool_parameter_type_by_name(value.get("type", "string"))
                            print(f"string_type: {value.get('type', 'string')}, real_type: {real_type}")
                            if not isinstance(parameters[name], real_type):
                                errors.append(
                                    f"Parameter {name} must be of type {value.get('type', None)}, but is {type(parameters[name])}."
                                )
                            elif value.get("enum", False) and parameters[name] not in value.get("enum", []):
                                errors.append(
                                    f"Parameter {name} must be one of {value.get('enum', [])}, but is {parameters[name]}."
                                )
                            if name in required_parameters:
                                required_parameters.remove(name)

                    if required_parameters:
                        errors.append(
                            f"Missing required parameters: {required_parameters}."
                        )

            check_counter += 1
            if errors:
                # try to let it fix itself
                message_history = []
                for message in self.wingman.messages:
                    role = message.role if hasattr(message, "role") else message.get("role", False)
                    if role in ["user", "assistant", "system"]:
                        message_history.append(
                            {
                                "role": role,
                                "content": message.content if hasattr(message, "content") else message.get("content", False),
                            }
                        )
                data = {
                    "set_timer": {
                        "delay": delay,
                        "function": function,
                        "parameters": parameters,
                    },
                    "message_history": message_history if len(message_history) <= 10 else message_history[:1] + message_history[-9:],
                    "tool_calls_definition": self.wingman.build_tools(),
                    "errors": errors,
                }

                messages = [
                    {
                        "role": "system",
                        "content": """
                            The set_time tool got called by a GPT request with parameters that are incomplete or do not match the given requirements.
                            Please adjust the parameters "delay", "function" and "parameters" to match the requirements of the tool.
                            Make use of the message_history to figure out missing parameters or wrong types.
                            And the tool_calls_definition to see the available tools and their requirements.

                            Provide me an answer in JSON format with the following structure for example:
                            {
                                "delay": 10,
                                "function": "function_name",
                                "parameters": {
                                    "parameter_name": "parameter_value"
                                }
                            }
                        """,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(data, indent=4)
                    },
                ]
                json_retry = 0
                max_json_retries = 1
                valid_json = False
                while not valid_json and json_retry < max_json_retries:
                    completion = await self.gpt_call(messages)
                    data = completion.choices[0].message.content
                    messages.append(
                        {
                            "role": "assistant",
                            "content": data,
                        }
                    )
                    # check if data is valid json
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        messages.append(
                            {
                                "role": "user",
                                "content": "Data is not valid JSON. Please provide valid JSON data.",
                            }
                        )
                        json_retry += 1
                    else:
                        valid_json = True
                        delay = data.get("delay", False)
                        function = data.get("function", False)
                        parameters = data.get("parameters", {})

        if errors:
            return f"""
                No timer set. Communicate these errors to the user.
                But make sure to align them with the message history so far: {errors}
            """

        # generate a unique id for the timer
        letters_and_digits = string.ascii_letters + string.digits
        timer_id = ''.join(random.choice(letters_and_digits) for _ in range(10))

        # set timer
        current_time = time.time()
        self.timers[timer_id] = [delay, function, parameters, current_time]

        # time execution
        def timed_execution(timer_id: str):
            async def execute_timer(timer_id: str) -> None:
                if timer_id not in self.timers:
                    print(f"Timer with id {timer_id} not found.")
                    return
                timer = self.timers[timer_id]
                delay = timer[0]
                function = timer[1]
                parameters = timer[2]

                await asyncio.sleep(delay)

                if timer_id not in self.timers:
                    print(f"Timer with id {timer_id} not found.")
                    return

                print(f"Executing timer with id {timer_id}: {function} with parameters {parameters}.")
                response = await self.wingman.execute_command_by_function_call(function, parameters)
                if(response):
                    summary = await self._summarize_timer_execution(function, parameters, response)
                    self.wingman.add_assistant_message(summary)
                    await printr.print_async(
                        f"{summary}",
                        color=LogType.POSITIVE,
                        source=LogSource.WINGMAN,
                        source_name=self.wingman.name,
                        skill_name=self.name,
                    )
                    await self.wingman.play_to_user(summary, True)
                del self.timers[timer_id]

            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(execute_timer(timer_id))
            new_loop.close()
        threading.Thread(target=timed_execution, args=(timer_id,)).start()

        print(f"Setting timer for {delay} seconds.")
        print(f"Function to execute: {function}")
        print(f"Parameters: {parameters}")

        return f"Timer set with id {timer_id}.\n\n{await self.get_timer_status()}"
    
    async def _summarize_timer_execution(self, function: str, parameters: dict[str, any], response: str) -> str:
        self.wingman.messages.append(
            {
                "role": "user",
                "content": f"""
                    Timed "{function}" with "{parameters}" was executed.
                    Summarize the respone while you must stay in character!
                    Dont mention it was a function call, go by the meaning:
                    {response}
                """,
            },
        )
        await self.wingman.add_context(self.wingman.messages)
        completion = await self.gpt_call(self.wingman.messages)
        answer = (
            completion.choices[0].message.content
            if completion and completion.choices
            else ""
        )
        return answer

    async def get_timer_status(self) -> list[dict[str, any]]:
        timers = []
        for timer_id, timer in self.timers.items():
            timers.append(
                {
                    "id": timer_id,
                    "delay": timer[0],
                    "remaining_time_in_seconds": round(max(0, timer[0] - (time.time() - timer[3]))),
                }
            )
        print(f"Running timers: {timers}")
        return timers

    async def cancel_timer(self, timer_id: str) -> str:
        if timer_id not in self.timers:
            return f"Timer with id {timer_id} not found."
        del self.timers[timer_id]
        print(f"Timer with id {timer_id} cancelled.")
        return f"Timer with id {timer_id} cancelled.\n\n{await self.get_timer_status()}"

    async def reminder(self, message: str = None) -> str:
        if not message:
            return "No reminder content set."
        print("Reminder played to user.")
        return message
