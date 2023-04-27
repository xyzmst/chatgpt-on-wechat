# encoding:utf-8

import plugins
from bridge.bridge import Bridge
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common import const
from common.expired_dict import ExpiredDict
from common.log import logger
from config import conf
from plugins import *


# https://github.com/bupticybee/ChineseAiDungeonChatGPT
class StoryTeller:
    def __init__(self, bot, sessionid, story):
        self.bot = bot
        self.sessionid = sessionid
        bot.sessions.clear_session(sessionid)
        self.first_interact = True
        self.story = story
        self.story_list = []

    def reset(self):
        self.bot.sessions.clear_session(self.sessionid)
        self.first_interact = True
        self.story_list = []

    def action(self, user_action, received_msg):
        if user_action[-1] != "。":
            user_action = user_action + "。"
        if self.first_interact:
            prompt = (
                """现在开始文字冒险游戏。请在回复时控制节奏，描述当前场景中的人物、地点、氛围等细节。每次回复时，请确保描述完整的场景细节，并控制回复长度在四到六句话之间。请注意，要求输出的内容不要偏离当前故事情节。
            开头是，"""
                + self.story
                + " "
                + user_action
            )
            self.story_list.append(self.story)
            self.story_list.append(user_action)
            self.first_interact = False
        else:
            prompt = (
                    """继续，一次只需要续写四到六句话，总共就只讲5分钟内发生的事情。"""
                    + user_action
            )
            self.story_list.append(received_msg)
            self.story_list.append(user_action)
            if len(self.story_list) >= 2:
                prompt = (
                       self.story_list[-2] + "," + self.story_list[-1] + "请继续描述："
                )
            logger.debug("[StoryTeller] action prompt: %s" % prompt)
        return prompt


@plugins.register(
    name="Dungeon",
    desire_priority=0,
    namecn="文字冒险",
    desc="A plugin to play dungeon game",
    version="1.0",
    author="lanvent",
)
class Dungeon(Plugin):
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[Dungeon] inited")
        # 目前没有设计session过期事件，这里先暂时使用过期字典
        if conf().get("expires_in_seconds"):
            self.games = ExpiredDict(conf().get("expires_in_seconds"))
        else:
            self.games = dict()

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type != ContextType.TEXT:
            return
        bottype = Bridge().get_bot_type("chat")
        if bottype not in [const.OPEN_AI, const.CHATGPT, const.CHATGPTONAZURE]:
            return
        bot = Bridge().get_bot("chat")
        content = e_context["context"].content[:]
        last_msg = e_context.econtext['context'].kwargs['msg']
        receivedMsgs = e_context['channel'].receivedMsgs
        # 假设 messages 是一个 ExpiredDict 对象，包含多个 ChatMessage 对象
        max_time = float("-inf")  # 初始化最大时间为负无穷
        receivedMsg = None
        max_message = None  # 初始化最大消息为 None
        for key in receivedMsgs.keys():  # 遍历所有消息
            message = receivedMsgs.get(key)
            if max_time < message.create_time < last_msg.create_time:  # 如果该消息的创建时间比当前最大时间更晚
                max_time = message.create_time  # 更新最大时间
                max_message = message  # 更新最大消息
        if max_message is not None:  # 如果找到了最大时间的消息
            # 进行相应的操作，比如输出该消息的内容
            logger.info("[Dungeon] inited %s" % max_message.content)
            receivedMsg = max_message.content

        clist = e_context["context"].content.split(maxsplit=1)
        sessionid = e_context["context"]["session_id"]
        logger.debug("[Dungeon] on_handle_context. content: %s" % clist)
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        if clist[0] == f"{trigger_prefix}停止冒险":
            if sessionid in self.games:
                self.games[sessionid].reset()
                del self.games[sessionid]
                reply = Reply(ReplyType.INFO, "冒险结束!")
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS
        elif clist[0] == f"{trigger_prefix}开始冒险" or sessionid in self.games:
            if sessionid not in self.games or clist[0] == f"{trigger_prefix}开始冒险":
                if len(clist) > 1:
                    story = clist[1]
                else:
                    story = "你在树林里冒险，指不定会从哪里蹦出来一些奇怪的东西，你握紧手上的手枪，希望这次冒险能够找到一些值钱的东西，你往树林深处走去。"
                self.games[sessionid] = StoryTeller(bot, sessionid, story)
                reply = Reply(ReplyType.INFO, "冒险开始，你可以输入任意内容，让故事继续下去。故事背景是：" + story)
                e_context["reply"] = reply
                e_context.action = EventAction.BREAK_PASS  # 事件结束，并跳过处理context的默认逻辑
            else:
                prompt = self.games[sessionid].action(content, receivedMsg)
                e_context["context"].type = ContextType.TEXT
                e_context["context"].content = prompt
                e_context.action = EventAction.BREAK  # 事件结束，不跳过处理context的默认逻辑

    def get_help_text(self, **kwargs):
        help_text = "可以和机器人一起玩文字冒险游戏。\n"
        if kwargs.get("verbose") != True:
            return help_text
        trigger_prefix = conf().get("plugin_trigger_prefix", "$")
        help_text = f"{trigger_prefix}开始冒险 " + "背景故事: 开始一个基于{背景故事}的文字冒险，之后你的所有消息会协助完善这个故事。\n" + f"{trigger_prefix}停止冒险: 结束游戏。\n"
        if kwargs.get("verbose") == True:
            help_text += f"\n命令例子: '{trigger_prefix}开始冒险 你在树林里冒险，指不定会从哪里蹦出来一些奇怪的东西，你握紧手上的手枪，希望这次冒险能够找到一些值钱的东西，你往树林深处走去。'"
        return help_text
